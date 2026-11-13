"""Coach engine: local server (FastAPI + WebSocket) that orchestrates capture → local L1 → remote L2.

WebSocket protocol (/ws), JSON messages pushed to the UI:
  state          state of the services (capture, StreetCLIP, vision) and default help level
  capture        new capture: id, thumbnail (JPEG data URL), duration
  streetclip     level 1: top countries (local) and "where to look" to tell them apart (metas)
  vision_pending level 2 running (remote model)
  vision         level 2: clue sheet
  vision_error   level 2 failed
  labelled       capture added to the test set ("Where was it?"), with the updated progress
  lookfor        "where to look" recomputed for a capture, after a "Right" / "Wrong" verdict
  (streetclip.similar: Plonk It tips that look like the view, for each candidate country)
  tips_translated translations of the displayed tips, arriving afterwards ({hash: text})
  cloud          likely zones of the view for the map (grouped PLONK cloud), all and country by country
  freeze         view frozen to draw marks on it (the full-screen marks window opens)
  mark           a mark: enlarged crop (pending), then what the model read there (done) or the error
  verdict        what the marks prove together (local rules: alphabet, letters, places)
  mark_removed   a mark removed by the player
  locks          locks of the capture (country › region › city), rejections and suggested city
  similar        Plonk It tips of the locked country, if it was not among the candidates
  error          capture impossible
Triggers: POST /capture and /marks/freeze (UI buttons) or Unix socket (GNOME shortcuts,
see trigger.py).
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from collections import OrderedDict
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel, Field

from .analysis_log import AnalysisLog
from .borders import Borders
from .capture import (CaptureError, CaptureService, apply_crop_and_masks, data_url, new_id, prune_captures, save_png,
                      trim_padding)
from .locks_engine import LockRequest, LocksMixin, PlaceSearchRequest, RejectRequest
from .marks_engine import MarksMixin
from .config import USER_CONFIG, Config, load_config
from .dataset import Dataset, DatasetError, coords_of, progress
from .marks import DeleteRequest, FrameRequest, MarksRequest, uses
from .pagetop import FILE as PAGE_TOP_FILE, PageTop
from .places import Places
from .metas import MetaError, UserMetasError, judge_seed, load_metas, select_candidates, tiebreak
from .settings import RESTART, SettingsError, current, file_only, save
from .notify import Notifier
from .plonkit import CHECKED_FILE, PlonkitError, collect, load_tips
from .plonkit_ai import classify as classify_tips
from .plonkit_ai import translate as translate_tips
from .plonkit_index import TipIndex, similar_tips
from .paths import SOCKET_PATH
from .plonk import PlonkCloud, summarise
from . import apikey, i18n, paths, storage
from .streetclip import StreetClip
from .vision import VisionClient, VisionError

RECENT_FRAMES = 10  # raw captures kept in memory for "Where was it?"
TRANSLATE_BATCH = 3  # tips per translation call (the calls go out in parallel)
# Plonk It tips encoded per batch, the model's lock released between two: about 0.07 s per tip on a 4-core processor
# (4-core VM), so a capture waits 0.6 s at most; on a graphics card, the batch is the old one.
PLONKIT_BATCH_CPU, PLONKIT_BATCH_GPU = 8, 64
PRETRANSLATE_BATCH = 10  # tips per call of the ahead-of-time translation (short answer: less fragile JSON)


class ModelTestRequest(BaseModel):
    model: str = Field(min_length=3, max_length=120, pattern=r"^[\w.\-]+/[\w.\-]+$")


class LabelRequest(BaseModel):
    id: str = Field(max_length=32)
    country: str = Field(default="", max_length=2)  # optional if the link gives the position
    found: bool | None = None  # ignored if "guessed" is given: it follows from it
    guessed: str = Field(default="", max_length=2)  # country answered by the player, optional
    area: str = Field(default="", max_length=200)
    link: str = Field(default="", max_length=2000)  # Google Maps link of the true place (never opened: only read)


class ApiKeyRequest(BaseModel):
    key: str = Field(default="", max_length=300)  # empty: forget the key


class TruthRequest(BaseModel):
    link: str = Field(min_length=3, max_length=2000)


class EraseRequest(BaseModel):
    confirm: Literal["ERASE"]  # sent once the player typed the word shown: nothing goes on a stray click
    models: bool = False  # also the downloaded models (nothing personal)


class ClearRequest(BaseModel):
    id: Literal["villages", "places", "plonkit", "captures"]


class JudgeRequest(BaseModel):
    """Player's verdict on a seed clue (its id in metas_amorce.toml); id = displayed capture, to update it."""

    seed: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    verdict: Literal["right", "wrong"]
    id: str = Field(default="", max_length=32)


class Engine(MarksMixin, LocksMixin):
    def __init__(self, cfg: Config, settings_path: Path = USER_CONFIG) -> None:
        self.cfg = cfg
        i18n.set_language(cfg.coach.language)
        self.settings_path = settings_path  # file written by the Settings screen
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.notifier = Notifier(cfg.capture.notify, cfg.capture.sound)
        self.capture = CaptureService(on_state=self._on_capture_state, source=cfg.capture.source)
        self.page_top = PageTop(paths.CONFIG_DIR / PAGE_TOP_FILE)  # where the page starts below the browser's bars
        self.capture_message = i18n.t("srv.sharing_starting")
        self.capture_starting = True  # GNOME picker possibly open: neither active nor cut off
        self.streetclip: StreetClip | None = None
        self.streetclip_message = i18n.t("srv.model_loading")
        self.vision = VisionClient(cfg.vision)
        self.gpu_lock = asyncio.Lock()
        self.dataset = Dataset(cfg.dataset.path) if cfg.dataset.enabled else None
        self.recent: OrderedDict[str, dict[str, Any]] = OrderedDict()  # id → raw image, predicted countries
        self.last_id: str | None = None  # last analysis: the marks complete it
        # Frozen views waiting for marks, with the analysis they complete (set at freeze time).
        self.frozen: OrderedDict[str, tuple[Image.Image, str]] = OrderedDict()
        self.mark_slots = asyncio.Semaphore(cfg.marks.parallel)
        self.metas = []
        self.metas_message, self.metas_error = i18n.t("srv.off_f"), False
        self.load_metas()
        self.settings_lock = asyncio.Lock()
        # References to the level 2 tasks: without them, asyncio may free them midway.
        self.background: set[asyncio.Task] = set()
        # (tips, matrix of their vectors): replaced in a single block and read at once, because the search
        # runs in a thread while the background update may change the database.
        self.plonkit_base: tuple[list, Any] = ([], None)
        self.plonkit_status = "off" if not cfg.plonkit.enabled else "absent"  # absent, busy, ready, error, off
        self.plonkit_message = ""
        self.plonkit_task: asyncio.Task | None = None
        self.plonkit_index: TipIndex | None = None
        self.plonkit_summary = ""  # "4060 astuces, 84 pays": base of the ahead-of-time translation messages
        self.pretranslate_task: asyncio.Task | None = None
        self.plonk: PlonkCloud | None = None  # map cloud (PLONK), loaded after StreetCLIP
        self.plonk_message = i18n.t("srv.off") if not cfg.plonk.enabled else i18n.t("srv.waiting_clip")
        self.plonk_task: asyncio.Task | None = None
        self.borders: Borders | None = None  # Natural Earth borders: countries of the points, map outlines
        self.places: Places | None = None  # GeoNames place names (local rules of the marks)
        self.places_message = i18n.t("srv.off") if not cfg.rules.places else i18n.t("srv.waiting")
        self.places_task: asyncio.Task | None = None
        self.detail_tasks: dict[str, asyncio.Task] = {}  # full directory of a country, being downloaded
        self.detail_failed: set[str] = set()  # countries whose detail failed: no new attempt before a restart
        self.erased = False  # "Erase everything" done: nothing in memory is valid any more, restart expected

    def load_metas(self) -> None:
        self.metas, self.metas_message, self.metas_error = [], i18n.t("srv.off_f"), False
        if self.cfg.metas.enabled:
            try:
                self.metas = load_metas(
                    self.cfg.metas.user_path, self.cfg.metas.include_seed, self.cfg.streetclip.countries.values()
                )
                self.metas_message = i18n.t("srv.metas_loaded", n=len(self.metas))
            except (MetaError, ValueError) as exc:  # invalid my-metas.toml: reported without blocking
                self.metas_message, self.metas_error = i18n.t("srv.metas_unavailable", error=exc), True

    async def apply_settings(self, changes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Saves the settings then applies them on the fly (all the exposed settings allow it)."""
        async with self.settings_lock:
            try:
                new = await asyncio.to_thread(save, changes, self.settings_path)
            except SettingsError as exc:
                raise HTTPException(422, str(exc)) from exc
            old, self.cfg = self.cfg, new
            i18n.set_language(new.coach.language)
            self.notifier.enabled, self.notifier.sound = new.capture.notify, new.capture.sound
            self.vision = VisionClient(new.vision)
            if new.marks.parallel != old.marks.parallel:  # the readings in progress keep the old one
                self.mark_slots = asyncio.Semaphore(new.marks.parallel)
            if self.streetclip:
                labels = (new.streetclip.prompt, new.streetclip.countries)
                if labels != (old.streetclip.prompt, old.streetclip.countries):  # text vectors to recompute
                    async with self.gpu_lock:
                        await asyncio.to_thread(self.streetclip.set_labels, new.streetclip)
                else:
                    self.streetclip.cfg = new.streetclip
            if new.dataset.enabled != (self.dataset is not None):
                self.dataset = Dataset(new.dataset.path) if new.dataset.enabled else None
            self.load_metas()
            if self.plonk:
                self.plonk.cfg = new.plonk  # steps and points: read for each cloud
            if new.plonk.enabled and self.plonk is None:
                self.schedule_plonk()
            elif not new.plonk.enabled:
                self.plonk, self.plonk_message = None, i18n.t("srv.off")  # frees the video memory
            if new.plonkit.enabled and self.plonkit_status == "off":
                self.plonkit_status = "absent"
                self.schedule_plonkit(check=self.plonkit_due())
            elif not new.plonkit.enabled:
                self.plonkit_status, self.plonkit_message = "off", ""
            # Language changed, ahead-of-time translation re-enabled…: it resumes where the cache stops.
            if self.plonkit_status == "ready":
                self.schedule_pretranslate()
            if new.rules.places and self.places is None:
                self.schedule_places()
            if new.storage.max_cache_mb < old.storage.max_cache_mb:
                await self.evict_caches()
        await self.broadcast(self.state())
        restart = [f"{section}.{key}" for section, values in changes.items() for key in values
                   if key in RESTART.get(section, ())]
        return {"ok": True, "settings": current(self.cfg), "restart": restart}

    # --- broadcast -------------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        return {
            "type": "state",
            "capture": {
                "alive": self.capture.alive,
                "starting": self.capture_starting,
                "message": self.capture_message,
            },
            "streetclip": {"ready": self.streetclip is not None, "message": self.streetclip_message},
            "vision": {
                "enabled": self.cfg.vision.enabled,
                "ready": self.vision.ready,
                "model": self.cfg.vision.model,
                "key": apikey.hint(self.cfg.vision.api_key_env),  # where the key comes from, last 4 characters
            },
            "help_level": self.cfg.coach.help_level,
            "language": i18n.language(),  # the UI's language (en when coach.language has no catalog)
            "trust_proof": self.cfg.coach.trust_proof,
            "leader": {"min": self.cfg.coach.leader_min, "margin": self.cfg.coach.leader_margin},
            "metas": {
                "count": len(self.metas), "message": self.metas_message, "error": self.metas_error,
                "judge": self.cfg.metas.judge_buttons,
            },
            "dataset": {"enabled": self.dataset is not None, "ask_guessed": self.cfg.dataset.ask_guessed},
            "plonkit": {
                "enabled": self.cfg.plonkit.enabled, "status": self.plonkit_status, "message": self.plonkit_message,
                "tips": len(self.plonkit_tips),
            },
            "plonk": {"enabled": self.cfg.plonk.enabled, "ready": self.plonk is not None, "message": self.plonk_message},
            "marks": {"enabled": self.cfg.marks.enabled, "max": self.cfg.marks.max_marks,
                      **dict(zip(("uses", "not_yet"), uses(self.cfg.rules.scripts, self.cfg.rules.letters,
                                                           self.cfg.rules.places and self.places is not None),
                                 strict=True))},
            "places": {"enabled": self.cfg.rules.places, "ready": self.places is not None,
                       "message": self.places_message},
            "locks": {"enabled": self.cfg.locks.enabled},
            "map": {
                "enabled": self.cfg.map.enabled, "tile_url": self.cfg.map.tile_url,
                "attribution": self.cfg.map.attribution, "attribution_url": self.cfg.map.attribution_url,
                "tile_filter": self.cfg.map.tile_filter, "tile_filter_close": self.cfg.map.tile_filter_close,
                "close_zoom": self.cfg.map.close_zoom, "max_zoom": self.cfg.map.max_zoom,
            },
            "countries": sorted(self.cfg.streetclip.countries.values()),
            "erased": self.erased,  # "Erase everything" done: the engine is waiting to be restarted
        }

    async def broadcast(self, message: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)

    def _on_capture_state(self, alive: bool, message: str, interrupted: bool, starting: bool) -> None:
        """Called from the capture threads: we go back into the asyncio loop."""
        self.capture_message = message
        self.capture_starting = starting
        if interrupted:
            self.notifier.send(i18n.t("srv.sharing_stopped"), i18n.t("srv.sharing_restart"), error=True)
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(self.state()), self.loop)

    # --- lifecycle -------------------------------------------------------------------------
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.capture.start()
        if self.cfg.streetclip.enabled:
            try:
                self.streetclip = await asyncio.to_thread(StreetClip, self.cfg.streetclip)
                self.streetclip_message = i18n.t("srv.ready_on", device=self.streetclip.device)
            except Exception as exc:
                self.streetclip_message = i18n.t("srv.unavailable", error=exc)
        else:
            self.streetclip_message = i18n.t("srv.off")
        await self.broadcast(self.state())
        if self.cfg.plonk.enabled:
            self.schedule_plonk()
        if self.cfg.plonkit.enabled:
            self.schedule_plonkit(check=self.plonkit_due())
        if self.cfg.rules.places:
            self.schedule_places()

    async def stop(self) -> None:
        for task in (self.plonkit_task, self.plonk_task, self.pretranslate_task, self.places_task,
                     *self.detail_tasks.values()):
            if task:
                task.cancel()
        await asyncio.to_thread(self.capture.stop)

    # --- storage: sizes, limit of the caches that grow, "Empty" -----------------------------------
    async def evict_caches(self, keep: set[str] = frozenset()) -> list[str]:
        """Villages of the countries beyond the limit: the least recently used go (except keep)."""
        removed = await asyncio.to_thread(storage.evict, self.cfg.rules.places_path,
                                          self.cfg.storage.max_cache_mb * 1024 * 1024, set(keep))
        for country in removed:
            if self.places:
                self.places.remove_detail(country)
        return removed

    def storage_items(self) -> dict[str, Any]:
        items = storage.inventory(self.cfg.rules.places_path, self.cfg.plonkit.path, self.cfg.capture.path)
        return {"items": items, "max_cache_mb": self.cfg.storage.max_cache_mb}

    # --- "Erase everything" (GDPR) -------------------------------------------------------------------
    def _erase_targets(self) -> tuple[dict[str, list[Path]], list[Path], list[Path]]:
        cfg, rc = self.cfg, self.cfg.rules
        groups = {
            "account": storage.account_files(paths.CONFIG_DIR, self.settings_path, cfg.metas.user_path),
            "captures": storage.capture_files(cfg.capture.path),
            "dataset": storage.dataset_files(cfg.dataset.path),
            "plonkit": storage.plonkit_files(cfg.plonkit.path),
            "places": storage.village_files(rc.places_path) + storage.base_place_files(rc.places_path),
        }
        models = storage.model_dirs(paths.hf_hub_cache(), [cfg.streetclip.model, cfg.plonk.model])
        # Folders removed if they are empty afterwards (an unknown file keeps them).
        folders = [paths.CONFIG_DIR, paths.DATA_DIR, cfg.capture.path, cfg.dataset.path, cfg.dataset.path / "images",
                   cfg.dataset.path / "rounds", cfg.plonkit.path, cfg.plonkit.path / "raw", rc.places_path]
        return groups, models, folders

    def erase_plan(self) -> dict[str, Any]:
        groups, models, _ = self._erase_targets()
        return {"groups": storage.erase_plan(groups, models, storage.installed_engine())}

    async def erase_all(self, with_models: bool) -> dict[str, Any]:
        """Erases everything about you; the engine must then be restarted (the UI asks Tauri to)."""
        for task in (self.plonkit_task, self.pretranslate_task, self.places_task, self.plonk_task,
                     *self.detail_tasks.values()):
            if task and not task.done():
                task.cancel()
        if self.places:
            self.places.close()
        if self.plonkit_index:
            self.plonkit_index.close()
        self.places, self.plonkit_index, self.plonkit_base = None, None, ([], None)
        self.recent.clear()
        groups, models, folders = self._erase_targets()
        freed = await asyncio.to_thread(storage.erase, groups, models, with_models, folders)
        self.erased = True
        await self.broadcast(self.state())
        return {"ok": True, "freed": freed}

    async def clear_storage(self, what: str) -> dict[str, Any]:
        """Empties a storage item; only known files are deleted, never a folder."""
        rc = self.cfg.rules
        if what in ("villages", "places") and self.places:
            for country in list(self.places.details):
                self.places.remove_detail(country)
        files = storage.village_files(rc.places_path)
        if what == "places":
            if self.places:
                self.places.close()
            self.places = None
            self.places_message = i18n.t("srv.places_cleared")
            files += storage.base_place_files(rc.places_path)
        elif what == "plonkit":
            for task in (self.plonkit_task, self.pretranslate_task):
                if task and not task.done():
                    task.cancel()
            if self.plonkit_index:
                self.plonkit_index.close()
            self.plonkit_index, self.plonkit_base = None, ([], None)
            if self.cfg.plonkit.enabled:
                self.plonkit_status, self.plonkit_message = "absent", i18n.t("srv.plonkit_cleared")
            files = storage.plonkit_files(self.cfg.plonkit.path)
        elif what == "captures":
            files = storage.capture_files(self.cfg.capture.path)
        freed = await asyncio.to_thread(storage.remove, files)
        if what == "villages":
            self.places_message = self._places_summary()
        await self.broadcast(self.state())
        return {"ok": True, "freed": freed, **self.storage_items()}

    # --- PLONK: map cloud --------------------------------------------------------------------------
    def schedule_plonk(self) -> None:
        if self.plonk_task and not self.plonk_task.done():
            return
        self.plonk_task = asyncio.create_task(self.load_plonk())

    async def load_plonk(self) -> None:
        """Loads PLONK (and the borders) on StreetCLIP's graphics card, whose vector it reads."""
        if self.streetclip is None:
            self.plonk_message = i18n.t("srv.plonk_needs_clip")
            await self.broadcast(self.state())
            return
        self.plonk_message = "chargement…"
        await self.broadcast(self.state())
        try:
            if self.borders is None:
                self.borders = await asyncio.to_thread(Borders)
            cfg, device = self.cfg.plonk, self.streetclip.device
            async with self.gpu_lock:
                plonk = await asyncio.to_thread(PlonkCloud, cfg, device)
            if self.cfg.plonk.enabled:
                self.plonk, self.plonk_message = plonk, i18n.t("srv.ready_on", device=device)
            else:  # disabled during loading: we do not keep it
                self.plonk_message = i18n.t("srv.off")
        except Exception as exc:  # weights missing offline, video memory, borders file…
            self.plonk, self.plonk_message = None, i18n.t("srv.unavailable", error=f"{type(exc).__name__}: {exc}")[:300]
        await self.broadcast(self.state())

    async def _cloud(self, capture_id: str, cls) -> None:
        """PLONK cloud of the view, in the background after StreetCLIP: it never delays the help."""
        plonk, borders = self.plonk, self.borders
        if plonk is None or borders is None:
            return
        try:
            async with self.gpu_lock:
                cloud = await asyncio.to_thread(plonk.sample, cls)
            countries = await asyncio.to_thread(borders.countries_of, cloud.lat, cloud.lon)
            message = {"type": "cloud", "id": capture_id, **summarise(cloud, countries, plonk.cfg)}
        except Exception as exc:  # video memory full…: the map stays at country level
            message = {"type": "cloud", "id": capture_id, "error": i18n.t("srv.cloud_unavailable", error=type(exc).__name__)}
        await self._log(capture_id, cloud={k: v for k, v in message.items() if k not in ("type", "id")})
        await self.broadcast(message)

    # --- Plonk It ------------------------------------------------------------------------------
    @property
    def plonkit_tips(self) -> list:
        return self.plonkit_base[0]

    def plonkit_due(self) -> bool:
        """Was the last check of the guides list more than refresh_days days ago?"""
        try:
            last = float((self.cfg.plonkit.path / CHECKED_FILE).read_text())
        except (OSError, ValueError):
            return True
        return time.time() - last > self.cfg.plonkit.refresh_days * 86400

    def schedule_plonkit(self, check: bool) -> bool:
        """Starts the update in the background; False if one is already running."""
        if self.plonkit_task and not self.plonkit_task.done():
            return False
        self.plonkit_task = asyncio.create_task(self.refresh_plonkit(check))
        return True

    async def _plonkit_status(self, status: str, message: str) -> None:
        self.plonkit_status, self.plonkit_message = status, message
        await self.broadcast(self.state())

    async def refresh_plonkit(self, check: bool) -> None:
        """check: check the online list and reload the modified guides; then index and vectorise."""
        pc = self.cfg.plonkit
        if self.streetclip is None:
            await self._plonkit_status("error", i18n.t("srv.plonkit_needs_clip"))
            return
        try:
            fetched = None
            if check:
                await self._plonkit_status("busy", i18n.t("srv.plonkit_updating"))
                countries = set(self.cfg.streetclip.countries.values())
                stats = await asyncio.to_thread(collect, countries, pc.path, pc.delay_s, False, lambda *_: None)
                fetched = stats["fetched"]
            await self._plonkit_status("busy", i18n.t("srv.plonkit_indexing"))
            tips, matrix = await self._index_plonkit()
            self.plonkit_base = (tips, matrix)
            countries = len({t.country for t in tips})
            done = i18n.t("srv.plonkit_fetched", n=fetched) if fetched else ""
            summary = i18n.t("srv.plonkit_summary", tips=len(tips), countries=countries, fetched=done)
            await self._plonkit_status("ready" if tips else "absent", summary)
            self.plonkit_summary = summary
            await self._classify_plonkit(summary)
            self.schedule_pretranslate()
        except (PlonkitError, OSError, ValueError, sqlite3.Error) as exc:  # network, page changed, disk…
            # The previous database is kept if it exists: the coach carries on with the tips already known.
            await self._plonkit_status("ready" if self.plonkit_tips else "error", i18n.t("srv.plonkit_error", error=exc))
        except Exception as exc:  # background task: never leave the UI on "update running"
            await self._plonkit_status("ready" if self.plonkit_tips else "error",
                                       i18n.t("srv.plonkit_unexpected", error=type(exc).__name__))
            raise

    async def _classify_plonkit(self, summary: str) -> None:
        """Has the AI classify, in batches, the tips left without a category; resumes where it stopped."""
        pc, index = self.cfg.plonkit, self.plonkit_index
        if not (pc.ai_classify and self.vision.client and index):
            return
        pending = await asyncio.to_thread(index.unclassified)
        if not pending:
            return
        model, done = pc.ai_model or self.cfg.vision.model, 0
        for start in range(0, len(pending), pc.ai_batch):
            batch = pending[start:start + pc.ai_batch]
            await self._plonkit_status("ready", i18n.t("srv.classify_progress", summary=summary, done=done, total=len(pending)))
            try:
                found = await classify_tips(self.vision.client, model, batch)
            except Exception as exc:  # 429, timeout, model unavailable: we will resume at the next update
                await self._plonkit_status("ready", i18n.t("srv.classify_stopped", summary=summary, error=type(exc).__name__))
                break
            if found:  # usable answer: the tips it leaves aside stay "other" for good
                await asyncio.to_thread(index.store_ai_categories, {h: found.get(h, "other") for h, _ in batch})
                done += len(batch)
            # Batch without any valid answer (unreadable answer): nothing is remembered, it will be offered again.
            if start + pc.ai_batch < len(pending):
                await asyncio.sleep(pc.ai_pause_s)
        else:
            await self._plonkit_status("ready", i18n.t("srv.classify_done", summary=summary, n=done))
        self.plonkit_base = await asyncio.to_thread(index.load, self.cfg.streetclip.model)

    async def _index_plonkit(self):
        pc, model = self.cfg.plonkit, self.cfg.streetclip.model
        if self.plonkit_index is None:
            self.plonkit_index = TipIndex(pc.path / "plonkit.sqlite")
        index = self.plonkit_index
        tips = await asyncio.to_thread(load_tips, pc.path)
        await asyncio.to_thread(index.rebuild, tips, pc.keywords)
        missing = await asyncio.to_thread(index.missing_embeddings, model)
        # Short batches, the model's lock released between two: on a processor,
        # the 4,000 tips take minutes (5 on a 4-core VM) and a capture must not wait for them, only for one batch.
        # Each batch is stored at once: closing the app in the middle loses nothing.
        batch = PLONKIT_BATCH_GPU if self.streetclip.device == "cuda" else PLONKIT_BATCH_CPU
        shown = 0.0
        for start in range(0, len(missing), batch):
            if time.monotonic() - shown >= 1:  # progress at most once a second: every batch would flood the UI
                shown = time.monotonic()
                await self._plonkit_status("busy", i18n.t("srv.plonkit_preparing", done=start, total=len(missing)))
            chunk = missing[start:start + batch]
            async with self.gpu_lock:  # shares the model with the captures
                vectors = await asyncio.to_thread(self.streetclip.encode_texts, [text for _, text in chunk])
            await asyncio.to_thread(index.store_embeddings, model, zip([h for h, _ in chunk], vectors, strict=True))
        return await asyncio.to_thread(index.load, model)

    @property
    def translation_lang(self) -> str | None:
        """Target language of the tips, or None if they stay in English."""
        pc, lang = self.cfg.plonkit, self.cfg.coach.language
        return lang if pc.translate and lang != "en" and self.vision.client else None

    def similar(self, emb, pairs: list[tuple[str, float]], codes: list[str] | None = None
                ) -> dict[str, list[dict[str, Any]]]:
        """Plonk It tips closest to the view, for the plausible countries (or codes: the locked country),
        empty if disabled, with their translation if it is already cached. Called outside the loop: it reads
        the database."""
        pc, m = self.cfg.plonkit, self.cfg.metas
        tips, matrix = self.plonkit_base  # a single read: tips and matrix go together
        if not (pc.enabled and pc.similar_tips and tips and emb is not None):
            return {}
        if codes is None:
            codes = [c for c, _ in select_candidates(pairs, m.min_probability, m.max_candidates)]
        found = similar_tips(emb, tips, matrix, codes, pc.similar_per_country)
        lang = self.translation_lang
        cached = {}
        if lang and self.plonkit_index:
            cached = self.plonkit_index.translations([t.hash for items in found.values() for t, _ in items], lang)
        return {
            code: [{"id": t.hash, "text": t.text, "translated": cached.get(t.hash), "section": t.section,
                    "category": t.category, "url": t.url, "score": round(score, 3)} for t, score in items]
            for code, items in found.items() if items
        }

    async def _translate_tips(self, capture_id: str, items: list[tuple[str, str]], lang: str) -> None:
        """Translates the displayed tips that have no cached translation, then pushes the result to the UI.

        A single message per batch, whatever happens: the UI counts the batches to know when it is over.
        """
        pc = self.cfg.plonkit
        model, t0 = pc.ai_model or self.cfg.vision.model, time.perf_counter()
        try:
            found = await asyncio.wait_for(translate_tips(self.vision.client, model, items, lang),
                                           pc.translate_timeout_s)
            if found and self.plonkit_index:
                await asyncio.to_thread(self.plonkit_index.store_translations, lang, found)
            message = {"type": "tips_translated", "id": capture_id, "translations": found}
            if len(found) < len(items):  # unreadable or incomplete answer: the rest keeps its English
                message["error"] = i18n.t("srv.model_incomplete")
        except Exception as exc:  # timeout, 429…: the tips stay in English for this capture
            message = {"type": "tips_translated", "id": capture_id, "translations": {},
                       "error": i18n.t("srv.translation_unavailable", error=type(exc).__name__)}
        entry = self.recent.get(capture_id)
        if entry is not None:  # debug mode log: each batch, its duration, what it returned
            entry.setdefault("translation", []).append({
                "tips": len(items), "translated": len(message["translations"]),
                "seconds": round(time.perf_counter() - t0, 1), "error": message.get("error"),
            })
            await self._log(capture_id, translation=list(entry["translation"]))
        await self.broadcast(message)

    # --- ahead-of-time translation -------------------------------------------------------------
    def schedule_pretranslate(self) -> None:
        if self.pretranslate_task and not self.pretranslate_task.done():
            return
        self.pretranslate_task = asyncio.create_task(self.pretranslate())

    async def pretranslate(self) -> None:
        """Translates the whole database in the background, in batches, letting the running analyses go first.

        Without it, each round waits for the API for its tips (measured: 50 s to 2 min). Resumes where the cache
        stops; a failed batch is retried at the next start.
        """
        pc, index, lang = self.cfg.plonkit, self.plonkit_index, self.translation_lang
        if not (pc.enabled and pc.pretranslate and lang and index):
            return
        pending = await asyncio.to_thread(index.untranslated, lang)
        total, done = len(pending), 0
        for start in range(0, total, PRETRANSLATE_BATCH):
            while self.background:  # a running round goes first (analysis, marks, displayed translation)
                await asyncio.sleep(1)
            if not self.cfg.plonkit.pretranslate or self.translation_lang != lang:
                return  # settings changed meanwhile: the next scheduling will start again from the cache
            await self._plonkit_status("ready", i18n.t("srv.pretranslate_progress", summary=self.plonkit_summary, done=done,
                                                                total=total))
            batch = pending[start:start + PRETRANSLATE_BATCH]
            model = self.cfg.plonkit.ai_model or self.cfg.vision.model
            try:
                found = await asyncio.wait_for(translate_tips(self.vision.client, model, batch, lang),
                                               max(self.cfg.plonkit.translate_timeout_s, 60))
            except Exception as exc:  # 429, timeout: we stop there, resume at the next start
                await self._plonkit_status(
                    "ready", i18n.t("srv.pretranslate_stopped", summary=self.plonkit_summary, error=type(exc).__name__))
                return
            if found:
                await asyncio.to_thread(index.store_translations, lang, found)
            done += len(found)
            await asyncio.sleep(self.cfg.plonkit.ai_pause_s)
        await self._plonkit_status("ready", i18n.t("srv.pretranslate_done", summary=self.plonkit_summary, n=done)
                                   if total else self.plonkit_summary)

    # --- analysis --------------------------------------------------------------------------
    async def _grab(self) -> tuple[Image.Image | None, str]:
        """Image of the shared window (black padding trimmed), or None and the error (already reported) if the sharing
        does not respond."""
        try:
            return await asyncio.to_thread(lambda: trim_padding(self.capture.grab())), ""
        except CaptureError as exc:
            await asyncio.to_thread(self.notifier.send, i18n.t("srv.capture_failed"), str(exc), error=True)
            await self.broadcast({"type": "error", "message": str(exc)})
            return None, str(exc)

    async def analyse(self) -> dict[str, Any]:
        capture_id = new_id()
        t0 = time.perf_counter()
        frame, error = await self._grab()
        if frame is None:
            return {"ok": False, "error": error}

        self.recent[capture_id] = {"frame": frame, "predicted": "", "scores": [], "log": None, "marks": [],
                                   "at": datetime.now().isoformat(timespec="seconds")}
        self.last_id = capture_id
        while len(self.recent) > RECENT_FRAMES:
            self.recent.popitem(last=False)
        guessed_crop = False
        if self.cfg.capture.crop:  # set by hand in config.toml
            view = apply_crop_and_masks(frame, self.cfg.capture.crop, self.cfg.capture.masks)
        else:  # the browser's bars (tab titles, address, bookmarks) never go to the models or the NVIDIA API
            await asyncio.to_thread(self.page_top.learn, frame)
            page, guessed_crop = self.page_top.crop(frame)
            view = apply_crop_and_masks(page, [], self.cfg.capture.masks)
        capture_ms = (time.perf_counter() - t0) * 1000
        if self.cfg.debug.enabled:
            await self._start_log(capture_id, f"capture-{capture_id}.png" if self.cfg.capture.save_to_disk else None)
        task = asyncio.create_task(self._keep_capture(capture_id, view, capture_ms))  # the models do not wait for it
        self.background.add(task)
        task.add_done_callback(self.background.discard)
        await self.broadcast({
            "type": "capture", "id": capture_id, "at": datetime.now().isoformat(timespec="seconds"),
            "thumbnail": await asyncio.to_thread(data_url, view), "ms": round(capture_ms),
            "guessed_crop": guessed_crop,
        })

        if self.cfg.vision.enabled:  # level 2 in parallel: it is slow, we do not wait for it
            task = asyncio.create_task(self._vision(capture_id, view))
            self.background.add(task)
            task.add_done_callback(self.background.discard)

        if self.streetclip:
            try:
                async with self.gpu_lock:
                    scores, ms, emb, cls = await asyncio.to_thread(self.streetclip.analyse, view)
            except Exception as exc:  # GPU memory full, driver…
                await self.broadcast({"type": "error", "message": i18n.t("srv.level1_unavailable", error=exc)})
                return {"ok": False, "id": capture_id, "error": str(exc)}
            pairs = [(s.code, s.probability) for s in scores]
            if capture_id in self.recent and scores:
                self.recent[capture_id].update(predicted=scores[0].code, scores=pairs, emb=emb)
            similar = await asyncio.to_thread(self.similar, emb, pairs)
            if capture_id in self.recent:  # countries whose tips have already been sent (lock: see locks_engine)
                self.recent[capture_id]["tips_for"] = set(similar)
                locks = self.recent[capture_id].get("locks")
                if locks and locks.country() and locks.country() not in similar:  # locked before the computation ended
                    task = asyncio.create_task(self._tips_for(capture_id, locks.country()))
                    self.background.add(task)
                    task.add_done_callback(self.background.discard)
            missing = list({tip["id"]: tip["text"] for tips in similar.values() for tip in tips
                            if tip["translated"] is None}.items())
            lang = self.translation_lang
            await self._log(capture_id, streetclip={
                "ms": round(ms), "scores": [s.__dict__ for s in scores],
                "lookfor": [lf.label for lf in self.look_for(pairs)],
                "similar": {code: [t["text"][:120] for t in tips] for code, tips in similar.items()},
            })
            await self.broadcast({
                "type": "streetclip", "id": capture_id, "ms": round(ms),
                "scores": [s.__dict__ for s in scores],
                "lookfor": [asdict(lf) for lf in self.look_for(pairs)],
                "similar": similar, "translating": bool(lang and missing),
                # Number of translation batches: a "tips_translated" message will arrive for each.
                "batches": -(-len(missing) // TRANSLATE_BATCH) if lang else 0,
                "cloud": self.plonk is not None and cls is not None,  # cloud announced: the map waits for it
            })
            if self.plonk is not None and cls is not None:
                task = asyncio.create_task(self._cloud(capture_id, cls))
                self.background.add(task)
                task.add_done_callback(self.background.discard)
            if lang and missing:  # in parallel, like level 2: the English shows first
                # Small simultaneous batches (~10 s each): each translation shows as soon as it arrives.
                for start in range(0, len(missing), TRANSLATE_BATCH):
                    task = asyncio.create_task(
                        self._translate_tips(capture_id, missing[start:start + TRANSLATE_BATCH], lang))
                    self.background.add(task)
                    task.add_done_callback(self.background.discard)
        return {"ok": True, "id": capture_id}

    async def _keep_capture(self, capture_id: str, view: Image.Image, capture_ms: float) -> None:
        """The copy of the analysed view on disk, then the "capture taken" notification with it. Run while the models
        work: a PNG takes 0.35 s at 1920 px wide and 1.3 s in 4K."""
        saved = None
        try:
            if self.cfg.capture.save_to_disk:
                saved = await asyncio.to_thread(save_png, view, self.cfg.capture.path, f"capture-{capture_id}")
            if (self.cfg.capture.save_to_disk or self.cfg.debug.enabled) and self.cfg.capture.keep_last:
                # Also in debug mode without capture copies: the logs alone must not pile up.
                await asyncio.to_thread(prune_captures, self.cfg.capture.path, self.cfg.capture.keep_last)
        except OSError:  # disk full, folder forbidden: the analysis carries on without its copy
            pass
        await asyncio.to_thread(self.notifier.send, i18n.t("srv.capture_taken"), f"{capture_ms:.0f} ms", image=saved)

    def look_for(self, scores: list[tuple[str, float]]):
        """Clue categories that tell a view's plausible countries apart (empty without metas)."""
        m = self.cfg.metas
        return self.separate(select_candidates(scores, m.min_probability, m.max_candidates), m.max_categories)

    def separate(self, candidates: list[tuple[str, float]], max_categories: int):
        """Tie-break between these particular candidates, according to the loaded metas and the settings."""
        if not self.metas:
            return []
        m = self.cfg.metas
        return tiebreak(
            candidates, self.metas, max_categories,
            looks=m.category_looks, weights=m.category_weights, max_looks=m.max_looks if m.show_looks else 0,
        )

    async def judge(self, req: JudgeRequest) -> dict[str, Any]:
        """"Right" / "Wrong" on a seed clue: written to my-metas.toml, then the metas are reloaded."""
        if not (self.cfg.metas.enabled and self.cfg.metas.judge_buttons):
            raise HTTPException(409, i18n.t("srv.verdicts_off"))
        async with self.settings_lock:
            try:
                await asyncio.to_thread(
                    judge_seed, self.cfg.metas.user_path, req.seed, req.verdict,
                    self.cfg.streetclip.countries.values(),
                )
            except UserMetasError as exc:  # the player's file must be fixed by hand
                raise HTTPException(409, str(exc)) from exc
            except MetaError as exc:  # clue not in the seed
                raise HTTPException(422, str(exc)) from exc
            self.load_metas()
        await self.broadcast(self.state())
        entry = self.recent.get(req.id)
        if entry and entry["scores"]:
            lookfor = [asdict(lf) for lf in self.look_for(entry["scores"])]
            await self.broadcast({"type": "lookfor", "id": req.id, "lookfor": lookfor})
        return {"ok": True}

    async def truth(self, link: str) -> dict[str, Any]:
        """True place from a Google Maps link: position, country (local borders), region (closest place)."""
        found = coords_of(link)
        if found is None:
            raise HTTPException(422, i18n.t("srv.no_coords"))
        lat, lon = found
        if self.borders is None:
            self.borders = await asyncio.to_thread(Borders)
        [country] = await asyncio.to_thread(self.borders.countries_of, [lat], [lon])
        region, region_name = "", ""
        if country and self.places is not None:
            near = await asyncio.to_thread(self.places.around, lat, lon, 30.0, country)
            region = next((r for _, _, r, *_ in near if r), "")
            region_name = await asyncio.to_thread(self.places.region_name, region) if region else ""
        return {"lat": lat, "lon": lon, "country": country, "region": region, "region_name": region_name}

    def round_data(self, entry: dict[str, Any]) -> dict[str, Any]:
        """What the coach had read and concluded during the round: replayed later by the bench (bench.py)."""
        locks = entry.get("locks")
        return {
            "at": entry.get("at"),
            "scores": [list(s) for s in (entry.get("scores") or [])[:5]],
            "marks": [{k: m.get(k) for k in ("n", "text", "object", "unreadable")}
                      for m in entry.get("marks", []) if m.get("status") == "done"],
            "verdict": {k: (entry.get("verdict") or {}).get(k) for k in ("country", "level", "location")},
            "locks": {**locks.as_dict(), "events": list(locks.events)} if locks else None,
        }

    async def label(self, req: LabelRequest) -> dict[str, Any]:
        if self.dataset is None:
            raise HTTPException(409, i18n.t("srv.dataset_off"))
        country, guessed = req.country.upper(), req.guessed.upper()
        where = await self.truth(req.link) if req.link.strip() else None
        if where and where["country"]:
            if country and country != where["country"]:
                raise HTTPException(422, i18n.t("srv.link_elsewhere", found=where["country"], country=country))
            country = where["country"]
        known = set(self.cfg.streetclip.countries.values())
        if country not in known or (guessed and guessed not in known):
            raise HTTPException(422, i18n.t("srv.unknown_country"))
        entry = self.recent.get(req.id)
        if entry is None:
            raise HTTPException(404, i18n.t("srv.capture_unknown"))
        try:
            saved = await asyncio.to_thread(
                self.dataset.add, req.id, entry["frame"], country,
                found=req.found, predicted=entry["predicted"], guessed=guessed, area=req.area,
                lat=where["lat"] if where else None, lon=where["lon"] if where else None,
                region=where["region"] if where else "", round_data=self.round_data(entry),
            )
        except DatasetError as exc:
            raise HTTPException(422, str(exc)) from exc
        await self._log(req.id, label={"country": country, "guessed": guessed, "found": saved.found, "area": req.area,
                                       "lat": saved.lat, "lon": saved.lon, "region": saved.region})
        prog = await self.progress()
        await self.broadcast({"type": "labelled", "id": req.id, "country": country, "guessed": guessed,
                              "found": saved.found, "progress": prog})
        return {"ok": True, "progress": prog}

    async def progress(self) -> dict[str, Any]:
        if self.dataset is None:
            return {}
        prog = asdict(progress(await asyncio.to_thread(self.dataset.labels)))
        prog["confusions"] = prog["confusions"][: self.cfg.dataset.max_confusions]
        for c in prog["confusions"]:  # what separates the two confused countries, according to your metas and the seed
            pair = [(c["country"], 0.5), (c["guessed"], 0.5)]
            c["lookfor"] = [asdict(lf) for lf in self.separate(pair, max_categories=2)]
        return prog

    async def _vision(self, capture_id: str, view: Image.Image) -> None:
        await self.broadcast({"type": "vision_pending", "id": capture_id, "model": self.cfg.vision.model})
        try:
            fiche, seconds = await self.vision.describe(view)
            await self._log(capture_id, vision={"model": self.cfg.vision.model, "seconds": round(seconds, 1),
                                                "fiche": fiche})
            await self.broadcast({
                "type": "vision", "id": capture_id, "model": self.cfg.vision.model,
                "seconds": round(seconds, 1), "fiche": fiche,
            })
        except VisionError as exc:
            await self._log(capture_id, vision={"model": self.cfg.vision.model, "error": str(exc)})
            await self.broadcast({"type": "vision_error", "id": capture_id, "error": str(exc)})

    # --- debug mode: log of each analysis ---------------------------------------------------------
    async def _start_log(self, capture_id: str, saved: str | None) -> None:
        cfg = self.cfg
        base = {
            "id": capture_id, "at": datetime.now().isoformat(timespec="seconds"),
            "capture": saved, "help_level": cfg.coach.help_level,
            "models": {"streetclip": cfg.streetclip.model, "vision": cfg.vision.model if cfg.vision.enabled else None,
                       "plonk": f"{cfg.plonk.model}@{cfg.plonk.revision[:7]}" if cfg.plonk.enabled else None},
        }
        try:
            log = await asyncio.to_thread(AnalysisLog, cfg.capture.path / f"capture-{capture_id}.json", base)
        except OSError:  # disk full, folder forbidden: the coach carries on without a log
            return
        if capture_id in self.recent:
            self.recent[capture_id]["log"] = log

    async def _log(self, capture_id: str, **fields: Any) -> None:
        entry = self.recent.get(capture_id)
        log = entry.get("log") if entry else None
        if log is not None:
            with suppress(OSError):  # a failed log must never break the analysis
                await asyncio.to_thread(log.update, **fields)


async def _unix_trigger(engine: Engine) -> asyncio.AbstractServer:
    """Unix socket restricted to the user (0600): receives "capture" from the GNOME shortcut."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            cmd = (await asyncio.wait_for(reader.readline(), 2)).decode(errors="replace").strip()
            if cmd in ("capture", "mark"):
                result = await (engine.analyse() if cmd == "capture" else engine.freeze())
                writer.write((f"OK {result['id']}" if result["ok"] else f"ERR {result['error']}").encode() + b"\n")
            else:
                writer.write(b"ERR unknown command\n")
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    SOCKET_PATH.unlink(missing_ok=True)
    old_umask = os.umask(0o177)
    try:
        return await asyncio.start_unix_server(handle, path=str(SOCKET_PATH))
    finally:
        os.umask(old_umask)


def create_app(cfg: Config | None = None, settings_path: Path = USER_CONFIG) -> FastAPI:
    cfg = cfg or load_config(settings_path)
    engine = Engine(cfg, settings_path)
    allowed = set(cfg.server.allowed_origins)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        trigger = await _unix_trigger(engine)
        start_task = asyncio.create_task(engine.start())
        try:
            yield
        finally:
            start_task.cancel()
            trigger.close()
            SOCKET_PATH.unlink(missing_ok=True)
            await engine.stop()

    app = FastAPI(title="GeoNesClick", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = engine  # access for the tests
    # Against "DNS rebinding": a booby-trapped domain pointing to 127.0.0.1 keeps its own Host.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    # JSON requests from the UI: CORS preflight limited to the allowed origins.
    app.add_middleware(
        CORSMiddleware, allow_origins=sorted(allowed), allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
    )

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        # A website open in the browser could target 127.0.0.1: any unknown origin is refused.
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed:
            return JSONResponse({"error": i18n.t("srv.origin_refused")}, status_code=403)
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return engine.state()

    @app.post("/capture")
    async def capture() -> dict[str, Any]:
        return await engine.analyse()

    @app.post("/marks/freeze")
    async def freeze() -> dict[str, Any]:
        """"Mark" button: freezes the view to draw a box around clues."""
        return await engine.freeze()

    @app.post("/marks/frame")
    async def frozen_frame(req: FrameRequest) -> dict[str, Any]:
        """Image of the frozen view, for the marks window. POST: the origin is always checked."""
        return await asyncio.to_thread(engine.frozen_image, req)

    @app.post("/marks/remove")
    async def remove_mark(req: DeleteRequest) -> dict[str, Any]:
        """Remove a mark whose reading is wrong: the conclusion is recomputed without it."""
        return await engine.remove_mark(req)

    @app.post("/locks")
    async def set_lock(req: LockRequest) -> dict[str, Any]:
        """The player locks a country, a region or a city ("I can see the Eiffel Tower: Paris")."""
        return await engine.set_lock(req)

    @app.post("/locks/reject")
    async def reject_lock(req: RejectRequest) -> dict[str, Any]:
        """✕ on a lock or on the suggested city: ruled out for the whole capture."""
        return await engine.reject_lock(req)

    @app.post("/locks/search")
    async def search_places(req: PlaceSearchRequest) -> dict[str, Any]:
        """Search for a region or a city in the local index (no network). POST: origin checked."""
        return await engine.search_places(req)

    @app.post("/marks")
    async def marks(req: MarksRequest) -> dict[str, Any]:
        """Marks drawn on the frozen view: cropped, enlarged, then transcribed by the vision model."""
        return await engine.add_marks(req)

    restart_lock = asyncio.Lock()  # two simultaneous restarts would fight over the GLib thread and the portal

    async def _restart(message: str, forget_window: bool) -> dict[str, Any]:
        async with restart_lock:
            engine.capture_message = message
            engine.capture_starting = True
            await engine.broadcast(engine.state())
            await asyncio.to_thread(engine.capture.restart, forget_window)
        return {"ok": True}

    @app.post("/capture/reselect")
    async def reselect() -> dict[str, Any]:
        """"Restart sharing" and "Change window": forgets the remembered window and reopens the GNOME picker.
        Stopping the sharing from GNOME is deliberate, often to change window, and a
        remembered window that no longer exists ("target not found") must not block the restart. Only the app's start
        resumes the remembered window without asking."""
        return await _restart(i18n.t("srv.pick_window"), forget_window=True)

    @app.post("/label")
    async def label(req: LabelRequest) -> dict[str, Any]:
        """"Where was it?": adds the capture to the test set with the real country."""
        return await engine.label(req)

    @app.post("/label/preview")
    async def label_preview(req: TruthRequest) -> dict[str, Any]:
        """What the link pasted into "Where was it?" says (country, region, position), before saving."""
        return await engine.truth(req.link)

    @app.post("/metas/judge")
    async def judge(req: JudgeRequest) -> dict[str, Any]:
        """The player confirms ("Right") or dismisses ("Wrong") a seed clue."""
        return await engine.judge(req)

    @app.post("/plonkit/refresh")
    async def plonkit_refresh() -> dict[str, Any]:
        """"Update" button: checks the guides list now, without waiting for refresh_days."""
        if not engine.cfg.plonkit.enabled:
            raise HTTPException(409, i18n.t("srv.plonkit_off"))
        if not engine.schedule_plonkit(check=True):
            raise HTTPException(409, i18n.t("srv.update_running"))
        return {"ok": True}

    @app.get("/map/countries")
    async def map_countries() -> JSONResponse:
        """Country outlines (Natural Earth 1:50m, public domain), with only their ISO code."""
        if engine.borders is None:
            engine.borders = await asyncio.to_thread(Borders)
        return JSONResponse(engine.borders.geojson, headers={"Cache-Control": "max-age=86400"})

    @app.get("/settings")
    async def get_settings() -> dict[str, Any]:
        return current(engine.cfg)

    @app.get("/settings/file-only")
    async def get_file_only() -> dict[str, Any]:
        """File-only settings (security), shown read-only with their reason."""
        return file_only(engine.cfg)

    @app.post("/settings")
    async def post_settings(changes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return await engine.apply_settings(changes)

    @app.post("/settings/api-key")
    async def set_api_key(req: ApiKeyRequest) -> dict[str, Any]:
        """API key entered in Settings: written to a file readable by you only (0600), never sent back."""
        name = engine.cfg.vision.api_key_env

        def store() -> None:
            if req.key.strip():
                apikey.save(name, req.key)
            else:  # field emptied: the key is forgotten
                apikey.forget(name)

        try:
            await asyncio.to_thread(store)
        except apikey.ApiKeyError as exc:
            raise HTTPException(422, str(exc)) from exc
        engine.vision = VisionClient(engine.cfg.vision)
        await engine.broadcast(engine.state())
        return {"ok": True, "key": apikey.hint(name)}

    @app.get("/models")
    async def models() -> dict[str, Any]:
        try:
            return {"models": await engine.vision.list_models()}
        except VisionError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/models/test")
    async def test_model(req: ModelTestRequest) -> dict[str, Any]:
        """Does the model accept images, and how fast does it answer?"""
        try:
            return {"ok": True, "seconds": round(await engine.vision.probe(req.model), 1)}
        except VisionError as exc:
            return {"ok": False, "error": str(exc)[:300]}

    @app.get("/storage")
    async def get_storage() -> dict[str, Any]:
        """What the coach keeps on disk, and the size of each item."""
        return await asyncio.to_thread(engine.storage_items)

    @app.get("/storage/erase")
    async def erase_plan() -> dict[str, Any]:
        """What "Erase everything" would delete, with the sizes (nothing is deleted here)."""
        return await asyncio.to_thread(engine.erase_plan)

    @app.post("/storage/erase")
    async def erase_all(req: EraseRequest) -> dict[str, Any]:
        """"Erase everything" (GDPR), confirmed by the typed word; then the UI restarts the engine, or has Tauri remove
        it (the "engine" box: only the engine installed by the AppImage, which cannot remove itself while running)."""
        return await engine.erase_all(req.models)

    @app.post("/storage/clear")
    async def clear_storage(req: ClearRequest) -> dict[str, Any]:
        return await engine.clear_storage(req.id)

    @app.get("/progress")
    async def get_progress() -> dict[str, Any]:
        return await engine.progress()

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        if websocket.headers.get("origin") not in allowed:
            await websocket.close(code=1008)  # policy violation
            return
        await websocket.accept()
        engine.clients.add(websocket)
        try:
            await websocket.send_json(engine.state())
            while True:
                await websocket.receive_text()  # the UI sends nothing for now
        except WebSocketDisconnect:
            pass
        finally:
            engine.clients.discard(websocket)

    return app


def main() -> None:
    import uvicorn

    cfg = load_config()
    with suppress(KeyboardInterrupt):
        uvicorn.run(create_app(cfg), host=cfg.server.host, port=cfg.server.port, log_level="info")
