"""Moteur du coach : serveur local (FastAPI + WebSocket) qui orchestre capture → N1 local → N2 distant.

Protocole WebSocket (/ws), messages JSON poussés vers l'interface :
  state          état des services (capture, StreetCLIP, vision) et niveau d'aide par défaut
  capture        nouvelle capture : id, miniature (data URL JPEG), durée
  streetclip     niveau 1 : top des pays (local) et « où regarder » pour les départager (metas)
  vision_pending niveau 2 en cours (modèle distant)
  vision         niveau 2 : fiche d'indices
  vision_error   niveau 2 en échec
  labelled       capture ajoutée au jeu de test (« C'était où ? »), avec la progression à jour
  lookfor        « où regarder » recalculé pour une capture, après un verdict « Juste » / « Faux »
  (streetclip.similar : astuces Plonk It qui ressemblent à la vue, pour chaque pays candidat)
  tips_translated traductions des astuces affichées, arrivées après coup ({empreinte: texte})
  cloud          zones probables de la vue pour la carte (nuage PLONK regroupé), toutes et pays par pays
  freeze         vue figée pour y tracer des marques (la fenêtre plein écran des marques s'ouvre)
  mark           une marque : découpe agrandie (pending), puis ce que le modèle y a lu (done) ou l'erreur
  verdict        ce que les marques prouvent ensemble (règles locales : alphabet, lettres, lieux)
  mark_removed   une marque retirée par le joueur
  locks          verrous de la capture (pays › région › ville), rejets et ville proposée
  similar        astuces Plonk It du pays verrouillé, s'il n'était pas parmi les candidats
  error          capture impossible
Déclencheurs : POST /capture et /marks/freeze (boutons de l'interface) ou socket Unix (raccourcis GNOME,
voir trigger.py).
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
from .capture import CaptureError, CaptureService, apply_crop_and_masks, data_url, new_id, prune_captures, save_png
from .locks_engine import LockRequest, LocksMixin, PlaceSearchRequest, RejectRequest
from .marks_engine import MarksMixin
from .config import USER_CONFIG, Config, load_config
from .dataset import Dataset, DatasetError, coords_of, progress
from .marks import DeleteRequest, FrameRequest, MarksRequest, uses
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
from . import storage
from .streetclip import StreetClip
from .vision import VisionClient, VisionError

RECENT_FRAMES = 10  # captures brutes gardées en mémoire pour « C'était où ? »
TRANSLATE_BATCH = 3  # astuces par appel de traduction (les appels partent en parallèle)
PRETRANSLATE_BATCH = 10  # astuces par appel de la traduction d'avance (réponse courte : JSON moins fragile)


class ModelTestRequest(BaseModel):
    model: str = Field(min_length=3, max_length=120, pattern=r"^[\w.\-]+/[\w.\-]+$")


class LabelRequest(BaseModel):
    id: str = Field(max_length=32)
    country: str = Field(default="", max_length=2)  # facultatif si le lien donne la position
    found: bool | None = None  # ignoré si « guessed » est donné : il s'en déduit
    guessed: str = Field(default="", max_length=2)  # pays répondu par le joueur, facultatif
    area: str = Field(default="", max_length=200)
    link: str = Field(default="", max_length=2000)  # lien Google Maps du vrai lieu (jamais ouvert : lu seulement)


class TruthRequest(BaseModel):
    link: str = Field(min_length=3, max_length=2000)


class ClearRequest(BaseModel):
    id: Literal["villages", "lieux", "plonkit", "captures"]


class JudgeRequest(BaseModel):
    """Verdict du joueur sur un indice de l'amorce ; id = capture affichée, pour la mettre à jour."""

    category: str = Field(max_length=20)
    hint: str = Field(min_length=1, max_length=300)
    verdict: Literal["right", "wrong"]
    id: str = Field(default="", max_length=32)


class Engine(MarksMixin, LocksMixin):
    def __init__(self, cfg: Config, settings_path: Path = USER_CONFIG) -> None:
        self.cfg = cfg
        self.settings_path = settings_path  # fichier écrit par l'écran Réglages
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.notifier = Notifier(cfg.capture.notify, cfg.capture.sound)
        self.capture = CaptureService(on_state=self._on_capture_state, source=cfg.capture.source)
        self.capture_message = "démarrage du partage d'écran…"
        self.capture_starting = True  # sélecteur GNOME éventuellement ouvert : ni actif ni coupé
        self.streetclip: StreetClip | None = None
        self.streetclip_message = "chargement du modèle…"
        self.vision = VisionClient(cfg.vision)
        self.gpu_lock = asyncio.Lock()
        self.dataset = Dataset(cfg.dataset.path) if cfg.dataset.enabled else None
        self.recent: OrderedDict[str, dict[str, Any]] = OrderedDict()  # id → image brute, pays prédits
        self.last_id: str | None = None  # dernière analyse : les marques la complètent
        # Vues figées en attente de marques, avec l'analyse qu'elles complètent (fixée au moment de figer).
        self.frozen: OrderedDict[str, tuple[Image.Image, str]] = OrderedDict()
        self.mark_slots = asyncio.Semaphore(cfg.marks.parallel)
        self.metas = []
        self.metas_message = "désactivées"
        self.load_metas()
        self.settings_lock = asyncio.Lock()
        # Références vers les tâches du niveau 2 : sans elles, asyncio peut les libérer en cours de route.
        self.background: set[asyncio.Task] = set()
        # (astuces, matrice de leurs vecteurs) : remplacé d'un seul bloc et lu en une fois, car la recherche
        # tourne dans un thread pendant que la mise à jour de fond peut changer la base.
        self.plonkit_base: tuple[list, Any] = ([], None)
        self.plonkit_status = "off" if not cfg.plonkit.enabled else "absent"  # absent, busy, ready, error, off
        self.plonkit_message = ""
        self.plonkit_task: asyncio.Task | None = None
        self.plonkit_index: TipIndex | None = None
        self.plonkit_summary = ""  # « 4060 astuces, 84 pays » : base des messages de la traduction d'avance
        self.pretranslate_task: asyncio.Task | None = None
        self.plonk: PlonkCloud | None = None  # nuage de la carte (PLONK), chargé après StreetCLIP
        self.plonk_message = "désactivé" if not cfg.plonk.enabled else "en attente de StreetCLIP"
        self.plonk_task: asyncio.Task | None = None
        self.borders: Borders | None = None  # frontières Natural Earth : pays des points, contours de la carte
        self.places: Places | None = None  # noms de lieux GeoNames (règles locales des marques)
        self.places_message = "désactivé" if not cfg.rules.places else "en attente"
        self.places_task: asyncio.Task | None = None
        self.detail_tasks: dict[str, asyncio.Task] = {}  # répertoire complet d'un pays, en cours de téléchargement
        self.detail_failed: set[str] = set()  # pays dont le détail a échoué : pas de nouvel essai avant redémarrage

    def load_metas(self) -> None:
        self.metas, self.metas_message = [], "désactivées"
        if self.cfg.metas.enabled:
            try:
                self.metas = load_metas(
                    self.cfg.metas.user_path, self.cfg.metas.include_seed, self.cfg.streetclip.countries.values()
                )
                self.metas_message = f"{len(self.metas)} metas chargées"
            except (MetaError, ValueError) as exc:  # fichier « mes metas » invalide : on le signale sans bloquer
                self.metas_message = f"metas indisponibles : {exc}"

    async def apply_settings(self, changes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """Enregistre les réglages puis les applique à chaud (tous les réglages exposés le permettent)."""
        async with self.settings_lock:
            try:
                new = await asyncio.to_thread(save, changes, self.settings_path)
            except SettingsError as exc:
                raise HTTPException(422, str(exc)) from exc
            old, self.cfg = self.cfg, new
            self.notifier.enabled, self.notifier.sound = new.capture.notify, new.capture.sound
            self.vision = VisionClient(new.vision)
            if new.marks.parallel != old.marks.parallel:  # les lectures en cours gardent l'ancien
                self.mark_slots = asyncio.Semaphore(new.marks.parallel)
            if self.streetclip:
                labels = (new.streetclip.prompt, new.streetclip.countries)
                if labels != (old.streetclip.prompt, old.streetclip.countries):  # vecteurs texte à recalculer
                    async with self.gpu_lock:
                        await asyncio.to_thread(self.streetclip.set_labels, new.streetclip)
                else:
                    self.streetclip.cfg = new.streetclip
            if new.dataset.enabled != (self.dataset is not None):
                self.dataset = Dataset(new.dataset.path) if new.dataset.enabled else None
            self.load_metas()
            if self.plonk:
                self.plonk.cfg = new.plonk  # pas et points : lus à chaque nuage
            if new.plonk.enabled and self.plonk is None:
                self.schedule_plonk()
            elif not new.plonk.enabled:
                self.plonk, self.plonk_message = None, "désactivé"  # libère la mémoire vidéo
            if new.plonkit.enabled and self.plonkit_status == "off":
                self.plonkit_status = "absent"
                self.schedule_plonkit(check=self.plonkit_due())
            elif not new.plonkit.enabled:
                self.plonkit_status, self.plonkit_message = "off", ""
            # Langue changée, traduction d'avance réactivée… : elle reprend là où le cache s'arrête.
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

    # --- diffusion -------------------------------------------------------------------------
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
            },
            "help_level": self.cfg.coach.help_level,
            "trust_proof": self.cfg.coach.trust_proof,
            "leader": {"min": self.cfg.coach.leader_min, "margin": self.cfg.coach.leader_margin},
            "metas": {
                "count": len(self.metas), "message": self.metas_message, "judge": self.cfg.metas.judge_buttons,
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
        }

    async def broadcast(self, message: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)

    def _on_capture_state(self, alive: bool, message: str, interrupted: bool) -> None:
        """Appelé depuis le thread GLib : on repasse dans la boucle asyncio."""
        self.capture_message = message
        self.capture_starting = False
        if interrupted:
            self.notifier.send("Partage d'écran interrompu", "Relance-le depuis la fenêtre du coach.", error=True)
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(self.state()), self.loop)

    # --- cycle de vie ----------------------------------------------------------------------
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.capture.start()
        if self.cfg.streetclip.enabled:
            try:
                self.streetclip = await asyncio.to_thread(StreetClip, self.cfg.streetclip)
                self.streetclip_message = f"prêt ({self.streetclip.device})"
            except Exception as exc:
                self.streetclip_message = f"indisponible : {exc}"
        else:
            self.streetclip_message = "désactivé"
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

    # --- stockage : tailles, limite des caches qui grossissent, « Vider » -----------------------------
    async def evict_caches(self, keep: set[str] = frozenset()) -> list[str]:
        """Villages des pays au-delà de la limite : les moins récemment utilisés partent (sauf keep)."""
        removed = await asyncio.to_thread(storage.evict, self.cfg.rules.places_path,
                                          self.cfg.storage.max_cache_mb * 1024 * 1024, set(keep))
        for country in removed:
            if self.places:
                self.places.remove_detail(country)
        return removed

    def storage_items(self) -> dict[str, Any]:
        items = storage.inventory(self.cfg.rules.places_path, self.cfg.plonkit.path, self.cfg.capture.path)
        return {"items": items, "max_cache_mb": self.cfg.storage.max_cache_mb}

    async def clear_storage(self, what: str) -> dict[str, Any]:
        """Vide un élément du stockage ; seuls des fichiers connus sont supprimés, jamais un dossier."""
        rc = self.cfg.rules
        if what in ("villages", "lieux") and self.places:
            for country in list(self.places.details):
                self.places.remove_detail(country)
        files = storage.village_files(rc.places_path)
        if what == "lieux":
            if self.places:
                self.places.close()
            self.places = None
            self.places_message = "vidé : retéléchargé au prochain démarrage"
            files += storage.base_place_files(rc.places_path)
        elif what == "plonkit":
            for task in (self.plonkit_task, self.pretranslate_task):
                if task and not task.done():
                    task.cancel()
            if self.plonkit_index:
                self.plonkit_index.close()
            self.plonkit_index, self.plonkit_base = None, ([], None)
            if self.cfg.plonkit.enabled:
                self.plonkit_status, self.plonkit_message = "absent", "vidé : recollecté au prochain démarrage"
            files = storage.plonkit_files(self.cfg.plonkit.path)
        elif what == "captures":
            files = storage.capture_files(self.cfg.capture.path)
        freed = await asyncio.to_thread(storage.remove, files)
        if what == "villages":
            self.places_message = self._places_summary()
        await self.broadcast(self.state())
        return {"ok": True, "freed": freed, **self.storage_items()}

    # --- PLONK : nuage de la carte -----------------------------------------------------------------
    def schedule_plonk(self) -> None:
        if self.plonk_task and not self.plonk_task.done():
            return
        self.plonk_task = asyncio.create_task(self.load_plonk())

    async def load_plonk(self) -> None:
        """Charge PLONK (et les frontières) sur la carte graphique de StreetCLIP, dont il lit le vecteur."""
        if self.streetclip is None:
            self.plonk_message = "StreetCLIP est nécessaire au nuage de la carte"
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
                self.plonk, self.plonk_message = plonk, f"prêt ({device})"
            else:  # désactivé pendant le chargement : on ne le garde pas
                self.plonk_message = "désactivé"
        except Exception as exc:  # poids absents hors ligne, mémoire vidéo, fichier de frontières…
            self.plonk, self.plonk_message = None, f"indisponible : {type(exc).__name__}: {exc}"[:300]
        await self.broadcast(self.state())

    async def _cloud(self, capture_id: str, cls) -> None:
        """Nuage PLONK de la vue, en arrière-plan après StreetCLIP : il ne retarde jamais l'aide."""
        plonk, borders = self.plonk, self.borders
        if plonk is None or borders is None:
            return
        try:
            async with self.gpu_lock:
                cloud = await asyncio.to_thread(plonk.sample, cls)
            countries = await asyncio.to_thread(borders.countries_of, cloud.lat, cloud.lon)
            message = {"type": "cloud", "id": capture_id, **summarise(cloud, countries, plonk.cfg)}
        except Exception as exc:  # mémoire vidéo saturée… : la carte reste au niveau des pays
            message = {"type": "cloud", "id": capture_id, "error": f"nuage indisponible ({type(exc).__name__})"}
        await self._log(capture_id, cloud={k: v for k, v in message.items() if k not in ("type", "id")})
        await self.broadcast(message)

    # --- Plonk It ------------------------------------------------------------------------------
    @property
    def plonkit_tips(self) -> list:
        return self.plonkit_base[0]

    def plonkit_due(self) -> bool:
        """Le dernier contrôle de la liste des guides date-t-il de plus de refresh_days jours ?"""
        try:
            last = float((self.cfg.plonkit.path / CHECKED_FILE).read_text())
        except (OSError, ValueError):
            return True
        return time.time() - last > self.cfg.plonkit.refresh_days * 86400

    def schedule_plonkit(self, check: bool) -> bool:
        """Lance la mise à jour en arrière-plan ; False si une est déjà en cours."""
        if self.plonkit_task and not self.plonkit_task.done():
            return False
        self.plonkit_task = asyncio.create_task(self.refresh_plonkit(check))
        return True

    async def _plonkit_status(self, status: str, message: str) -> None:
        self.plonkit_status, self.plonkit_message = status, message
        await self.broadcast(self.state())

    async def refresh_plonkit(self, check: bool) -> None:
        """check : contrôler la liste en ligne et recharger les guides modifiés ; puis indexer et vectoriser."""
        pc = self.cfg.plonkit
        if self.streetclip is None:
            await self._plonkit_status("error", "StreetCLIP est nécessaire pour comparer la vue aux astuces")
            return
        try:
            fetched = None
            if check:
                await self._plonkit_status("busy", "mise à jour des guides Plonk It…")
                countries = set(self.cfg.streetclip.countries.values())
                stats = await asyncio.to_thread(collect, countries, pc.path, pc.delay_s, False, lambda *_: None)
                fetched = stats["fetched"]
            await self._plonkit_status("busy", "indexation des astuces…")
            tips, matrix = await self._index_plonkit()
            self.plonkit_base = (tips, matrix)
            countries = len({t.country for t in tips})
            done = f", {fetched} guides mis à jour" if fetched else ""
            summary = f"{len(tips)} astuces, {countries} pays{done}"
            await self._plonkit_status("ready" if tips else "absent", summary)
            self.plonkit_summary = summary
            await self._classify_plonkit(summary)
            self.schedule_pretranslate()
        except (PlonkitError, OSError, ValueError, sqlite3.Error) as exc:  # réseau, page changée, disque…
            # On garde la base précédente si elle existe : le coach continue avec les astuces déjà connues.
            await self._plonkit_status("ready" if self.plonkit_tips else "error", f"Plonk It : {exc}")
        except Exception as exc:  # tâche de fond : ne jamais laisser l'interface sur « mise à jour en cours »
            await self._plonkit_status("ready" if self.plonkit_tips else "error",
                                       f"Plonk It : erreur inattendue ({type(exc).__name__})")
            raise

    async def _classify_plonkit(self, summary: str) -> None:
        """Classe par l'IA, par lots, les astuces restées sans catégorie ; reprend où il s'était arrêté."""
        pc, index = self.cfg.plonkit, self.plonkit_index
        if not (pc.ai_classify and self.vision.client and index):
            return
        pending = await asyncio.to_thread(index.unclassified)
        if not pending:
            return
        model, done = pc.ai_model or self.cfg.vision.model, 0
        for start in range(0, len(pending), pc.ai_batch):
            batch = pending[start:start + pc.ai_batch]
            await self._plonkit_status("ready", f"{summary} ; classement par l'IA : {done}/{len(pending)}")
            try:
                found = await classify_tips(self.vision.client, model, batch)
            except Exception as exc:  # 429, délai, modèle indisponible : on reprendra à la prochaine mise à jour
                await self._plonkit_status("ready", f"{summary} ; classement par l'IA interrompu ({type(exc).__name__})")
                break
            if found:  # réponse exploitable : les astuces qu'elle laisse de côté restent « autre » pour de bon
                await asyncio.to_thread(index.store_ai_categories, {h: found.get(h, "autre") for h, _ in batch})
                done += len(batch)
            # Lot sans aucune réponse valide (réponse illisible) : rien n'est mémorisé, il sera reproposé.
            if start + pc.ai_batch < len(pending):
                await asyncio.sleep(pc.ai_pause_s)
        else:
            await self._plonkit_status("ready", f"{summary} ; {done} astuces classées par l'IA")
        self.plonkit_base = await asyncio.to_thread(index.load, self.cfg.streetclip.model)

    async def _index_plonkit(self):
        pc, model = self.cfg.plonkit, self.cfg.streetclip.model
        if self.plonkit_index is None:
            self.plonkit_index = TipIndex(pc.path / "plonkit.sqlite")
        index = self.plonkit_index
        tips = await asyncio.to_thread(load_tips, pc.path)
        await asyncio.to_thread(index.rebuild, tips, pc.keywords)
        missing = await asyncio.to_thread(index.missing_embeddings, model)
        if missing:
            async with self.gpu_lock:  # partage la carte graphique avec les captures
                vectors = await asyncio.to_thread(self.streetclip.encode_texts, [text for _, text in missing])
            await asyncio.to_thread(index.store_embeddings, model, zip([h for h, _ in missing], vectors, strict=True))
        return await asyncio.to_thread(index.load, model)

    @property
    def translation_lang(self) -> str | None:
        """Langue cible des astuces, ou None si on les garde en anglais."""
        pc, lang = self.cfg.plonkit, self.cfg.coach.language
        return lang if pc.translate and lang != "en" and self.vision.client else None

    def similar(self, emb, pairs: list[tuple[str, float]], codes: list[str] | None = None
                ) -> dict[str, list[dict[str, Any]]]:
        """Astuces Plonk It les plus proches de la vue, pour les pays plausibles (ou codes : le pays verrouillé),
        vide si désactivé, avec leur traduction si elle est déjà en cache. Appelée hors de la boucle : elle lit
        la base."""
        pc, m = self.cfg.plonkit, self.cfg.metas
        tips, matrix = self.plonkit_base  # une seule lecture : astuces et matrice vont ensemble
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
        """Traduit les astuces affichées sans traduction en cache, puis pousse le résultat à l'interface.

        Un seul message par lot, quoi qu'il arrive : l'interface compte les lots pour savoir quand c'est fini.
        """
        pc = self.cfg.plonkit
        model, t0 = pc.ai_model or self.cfg.vision.model, time.perf_counter()
        try:
            found = await asyncio.wait_for(translate_tips(self.vision.client, model, items, lang),
                                           pc.translate_timeout_s)
            if found and self.plonkit_index:
                await asyncio.to_thread(self.plonkit_index.store_translations, lang, found)
            message = {"type": "tips_translated", "id": capture_id, "translations": found}
            if len(found) < len(items):  # réponse illisible ou incomplète : le reste garde son anglais
                message["error"] = "réponse du modèle incomplète"
        except Exception as exc:  # délai, 429… : les astuces restent en anglais pour cette capture
            message = {"type": "tips_translated", "id": capture_id, "translations": {},
                       "error": f"traduction indisponible ({type(exc).__name__})"}
        entry = self.recent.get(capture_id)
        if entry is not None:  # journal du mode débogage : chaque lot, sa durée, ce qu'il a rendu
            entry.setdefault("translation", []).append({
                "tips": len(items), "translated": len(message["translations"]),
                "seconds": round(time.perf_counter() - t0, 1), "error": message.get("error"),
            })
            await self._log(capture_id, translation=list(entry["translation"]))
        await self.broadcast(message)

    # --- traduction d'avance -------------------------------------------------------------------
    def schedule_pretranslate(self) -> None:
        if self.pretranslate_task and not self.pretranslate_task.done():
            return
        self.pretranslate_task = asyncio.create_task(self.pretranslate())

    async def pretranslate(self) -> None:
        """Traduit toute la base en arrière-plan, par lots, en laissant passer les analyses en cours.

        Sans elle, chaque manche attend l'API pour ses astuces (mesuré : 50 s à 2 min). Reprend où le cache
        s'arrête ; un lot raté est retenté au prochain démarrage.
        """
        pc, index, lang = self.cfg.plonkit, self.plonkit_index, self.translation_lang
        if not (pc.enabled and pc.pretranslate and lang and index):
            return
        pending = await asyncio.to_thread(index.untranslated, lang)
        total, done = len(pending), 0
        for start in range(0, total, PRETRANSLATE_BATCH):
            while self.background:  # une manche en cours passe d'abord (analyse, marques, traduction affichée)
                await asyncio.sleep(1)
            if not self.cfg.plonkit.pretranslate or self.translation_lang != lang:
                return  # réglages changés entre-temps : la prochaine planification repartira du cache
            await self._plonkit_status("ready", f"{self.plonkit_summary} ; traduction d'avance : {done}/{total}")
            batch = pending[start:start + PRETRANSLATE_BATCH]
            model = self.cfg.plonkit.ai_model or self.cfg.vision.model
            try:
                found = await asyncio.wait_for(translate_tips(self.vision.client, model, batch, lang),
                                               max(self.cfg.plonkit.translate_timeout_s, 60))
            except Exception as exc:  # 429, délai : on s'arrête là, reprise au prochain démarrage
                await self._plonkit_status(
                    "ready", f"{self.plonkit_summary} ; traduction d'avance interrompue ({type(exc).__name__})")
                return
            if found:
                await asyncio.to_thread(index.store_translations, lang, found)
            done += len(found)
            await asyncio.sleep(self.cfg.plonkit.ai_pause_s)
        await self._plonkit_status("ready", f"{self.plonkit_summary} ; {done} astuces traduites d'avance"
                                   if total else self.plonkit_summary)

    # --- analyse ---------------------------------------------------------------------------
    async def _grab(self) -> tuple[Image.Image | None, str]:
        """Image brute de la fenêtre partagée, ou None et l'erreur (déjà signalée) si le partage ne répond pas."""
        try:
            return await asyncio.to_thread(self.capture.grab), ""
        except CaptureError as exc:
            await asyncio.to_thread(self.notifier.send, "Capture impossible", str(exc), error=True)
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
        view = apply_crop_and_masks(frame, self.cfg.capture.crop, self.cfg.capture.masks)
        saved = None
        if self.cfg.capture.save_to_disk:
            saved = await asyncio.to_thread(save_png, view, self.cfg.capture.path, f"capture-{capture_id}")
        if (self.cfg.capture.save_to_disk or self.cfg.debug.enabled) and self.cfg.capture.keep_last:
            # Aussi en débogage sans copie des captures : les journaux seuls ne doivent pas s'accumuler.
            await asyncio.to_thread(prune_captures, self.cfg.capture.path, self.cfg.capture.keep_last)
        capture_ms = (time.perf_counter() - t0) * 1000
        if self.cfg.debug.enabled:
            await self._start_log(capture_id, saved)
        await asyncio.to_thread(self.notifier.send, "Capture prise", f"{capture_ms:.0f} ms", image=saved)
        await self.broadcast({
            "type": "capture", "id": capture_id, "at": datetime.now().isoformat(timespec="seconds"),
            "thumbnail": await asyncio.to_thread(data_url, view), "ms": round(capture_ms),
        })

        if self.cfg.vision.enabled:  # niveau 2 en parallèle : il est lent, on ne l'attend pas
            task = asyncio.create_task(self._vision(capture_id, view))
            self.background.add(task)
            task.add_done_callback(self.background.discard)

        if self.streetclip:
            try:
                async with self.gpu_lock:
                    scores, ms, emb, cls = await asyncio.to_thread(self.streetclip.analyse, view)
            except Exception as exc:  # mémoire GPU saturée, pilote…
                await self.broadcast({"type": "error", "message": f"Niveau 1 indisponible : {exc}"})
                return {"ok": False, "id": capture_id, "error": str(exc)}
            pairs = [(s.code, s.probability) for s in scores]
            if capture_id in self.recent and scores:
                self.recent[capture_id].update(predicted=scores[0].code, scores=pairs, emb=emb)
            similar = await asyncio.to_thread(self.similar, emb, pairs)
            if capture_id in self.recent:  # pays dont les astuces sont déjà envoyées (verrou : voir locks_engine)
                self.recent[capture_id]["tips_for"] = set(similar)
                locks = self.recent[capture_id].get("locks")
                if locks and locks.country() and locks.country() not in similar:  # verrouillé avant la fin du calcul
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
                # Nombre de lots de traduction : un message « tips_translated » arrivera pour chacun.
                "batches": -(-len(missing) // TRANSLATE_BATCH) if lang else 0,
                "cloud": self.plonk is not None and cls is not None,  # nuage annoncé : la carte l'attend
            })
            if self.plonk is not None and cls is not None:
                task = asyncio.create_task(self._cloud(capture_id, cls))
                self.background.add(task)
                task.add_done_callback(self.background.discard)
            if lang and missing:  # en parallèle, comme le niveau 2 : l'anglais s'affiche d'abord
                # Petits lots simultanés (~10 s chacun) : chaque traduction s'affiche dès qu'elle arrive.
                for start in range(0, len(missing), TRANSLATE_BATCH):
                    task = asyncio.create_task(
                        self._translate_tips(capture_id, missing[start:start + TRANSLATE_BATCH], lang))
                    self.background.add(task)
                    task.add_done_callback(self.background.discard)
        return {"ok": True, "id": capture_id}

    def look_for(self, scores: list[tuple[str, float]]):
        """Catégories d'indices qui départagent les pays plausibles d'une vue (vide sans metas)."""
        m = self.cfg.metas
        return self.separate(select_candidates(scores, m.min_probability, m.max_candidates), m.max_categories)

    def separate(self, candidates: list[tuple[str, float]], max_categories: int):
        """Départage de ces candidats-là, selon les metas chargées et les réglages."""
        if not self.metas:
            return []
        m = self.cfg.metas
        return tiebreak(
            candidates, self.metas, max_categories,
            looks=m.category_looks, weights=m.category_weights, max_looks=m.max_looks if m.show_looks else 0,
        )

    async def judge(self, req: JudgeRequest) -> dict[str, Any]:
        """« Juste » / « Faux » sur un indice de l'amorce : écrit dans mes-metas.toml puis recharge les metas."""
        if not (self.cfg.metas.enabled and self.cfg.metas.judge_buttons):
            raise HTTPException(409, "verdicts désactivés dans la configuration")
        async with self.settings_lock:
            try:
                await asyncio.to_thread(
                    judge_seed, self.cfg.metas.user_path, req.category, req.hint, req.verdict,
                    self.cfg.streetclip.countries.values(),
                )
            except UserMetasError as exc:  # le fichier du joueur est à corriger à la main
                raise HTTPException(409, str(exc)) from exc
            except MetaError as exc:  # indice absent de l'amorce
                raise HTTPException(422, str(exc)) from exc
            self.load_metas()
        await self.broadcast(self.state())
        entry = self.recent.get(req.id)
        if entry and entry["scores"]:
            lookfor = [asdict(lf) for lf in self.look_for(entry["scores"])]
            await self.broadcast({"type": "lookfor", "id": req.id, "lookfor": lookfor})
        return {"ok": True}

    async def truth(self, link: str) -> dict[str, Any]:
        """Vrai lieu d'après un lien Google Maps : position, pays (frontières locales), région (lieu le plus proche)."""
        found = coords_of(link)
        if found is None:
            raise HTTPException(422, "pas de coordonnées dans ce lien : colle le lien complet (pas un lien court "
                                     "maps.app.goo.gl), ou « latitude, longitude »")
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
        """Ce que le coach avait lu et conclu pendant la manche : rejoué ensuite par le banc (bench.py)."""
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
            raise HTTPException(409, "jeu de test désactivé dans la configuration")
        country, guessed = req.country.upper(), req.guessed.upper()
        where = await self.truth(req.link) if req.link.strip() else None
        if where and where["country"]:
            if country and country != where["country"]:
                raise HTTPException(422, f"le lien tombe en {where['country']}, pas en {country}")
            country = where["country"]
        known = set(self.cfg.streetclip.countries.values())
        if country not in known or (guessed and guessed not in known):
            raise HTTPException(422, "pays inconnu")
        entry = self.recent.get(req.id)
        if entry is None:
            raise HTTPException(404, "capture trop ancienne ou inconnue")
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
        for c in prog["confusions"]:  # ce qui sépare les deux pays confondus, d'après tes metas et l'amorce
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

    # --- mode débogage : journal de chaque analyse -------------------------------------------------
    async def _start_log(self, capture_id: str, saved: Path | None) -> None:
        cfg = self.cfg
        base = {
            "id": capture_id, "at": datetime.now().isoformat(timespec="seconds"),
            "capture": saved.name if saved else None, "help_level": cfg.coach.help_level,
            "models": {"streetclip": cfg.streetclip.model, "vision": cfg.vision.model if cfg.vision.enabled else None,
                       "plonk": f"{cfg.plonk.model}@{cfg.plonk.revision[:7]}" if cfg.plonk.enabled else None},
        }
        try:
            log = await asyncio.to_thread(AnalysisLog, cfg.capture.path / f"capture-{capture_id}.json", base)
        except OSError:  # disque plein, dossier interdit : le coach continue sans journal
            return
        if capture_id in self.recent:
            self.recent[capture_id]["log"] = log

    async def _log(self, capture_id: str, **fields: Any) -> None:
        entry = self.recent.get(capture_id)
        log = entry.get("log") if entry else None
        if log is not None:
            with suppress(OSError):  # un journal raté ne doit jamais casser l'analyse
                await asyncio.to_thread(log.update, **fields)


async def _unix_trigger(engine: Engine) -> asyncio.AbstractServer:
    """Socket Unix réservé à l'utilisateur (0600) : reçoit « capture » depuis le raccourci GNOME."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            cmd = (await asyncio.wait_for(reader.readline(), 2)).decode(errors="replace").strip()
            if cmd in ("capture", "mark"):
                result = await (engine.analyse() if cmd == "capture" else engine.freeze())
                writer.write((f"OK {result['id']}" if result["ok"] else f"ERR {result['error']}").encode() + b"\n")
            else:
                writer.write(b"ERR commande inconnue\n")
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
    app.state.engine = engine  # accès pour les tests
    # Contre le « DNS rebinding » : un domaine piégé qui pointerait vers 127.0.0.1 garde son propre Host.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    # Requêtes JSON de l'interface : pré-vérification CORS limitée aux origines autorisées.
    app.add_middleware(
        CORSMiddleware, allow_origins=sorted(allowed), allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
    )

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        # Un site web ouvert dans le navigateur pourrait viser 127.0.0.1 : on refuse toute origine inconnue.
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed:
            return JSONResponse({"error": "origine refusée"}, status_code=403)
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return engine.state()

    @app.post("/capture")
    async def capture() -> dict[str, Any]:
        return await engine.analyse()

    @app.post("/marks/freeze")
    async def freeze() -> dict[str, Any]:
        """Bouton « Marquer » : fige la vue pour y entourer des indices."""
        return await engine.freeze()

    @app.post("/marks/frame")
    async def frozen_frame(req: FrameRequest) -> dict[str, Any]:
        """Image de la vue figée, pour la fenêtre des marques. POST : l'origine est toujours contrôlée."""
        return await asyncio.to_thread(engine.frozen_image, req)

    @app.post("/marks/remove")
    async def remove_mark(req: DeleteRequest) -> dict[str, Any]:
        """Retirer une marque dont la lecture est fausse : la conclusion est recalculée sans elle."""
        return await engine.remove_mark(req)

    @app.post("/locks")
    async def set_lock(req: LockRequest) -> dict[str, Any]:
        """Le joueur verrouille un pays, une région ou une ville (« je vois la tour Eiffel : Paris »)."""
        return await engine.set_lock(req)

    @app.post("/locks/reject")
    async def reject_lock(req: RejectRequest) -> dict[str, Any]:
        """✕ sur un verrou ou sur la ville proposée : écarté pour toute la capture."""
        return await engine.reject_lock(req)

    @app.post("/locks/search")
    async def search_places(req: PlaceSearchRequest) -> dict[str, Any]:
        """Recherche d'une région ou d'une ville dans l'index local (aucun réseau). POST : origine contrôlée."""
        return await engine.search_places(req)

    @app.post("/marks")
    async def marks(req: MarksRequest) -> dict[str, Any]:
        """Marques tracées sur la vue figée : découpées, agrandies, puis transcrites par le modèle de vision."""
        return await engine.add_marks(req)

    restart_lock = asyncio.Lock()  # deux relances simultanées se disputeraient le thread GLib et le portail

    async def _restart(message: str, forget_window: bool) -> dict[str, Any]:
        async with restart_lock:
            engine.capture_message = message
            engine.capture_starting = True
            await engine.broadcast(engine.state())
            await asyncio.to_thread(engine.capture.restart, forget_window)
        return {"ok": True}

    @app.post("/capture/restart")
    async def restart() -> dict[str, Any]:
        return await _restart("relance du partage d'écran…", forget_window=False)

    @app.post("/capture/reselect")
    async def reselect() -> dict[str, Any]:
        """Changer de fenêtre (autre navigateur, écran, résolution) : rouvre le sélecteur de GNOME."""
        return await _restart("choisis la fenêtre du jeu à partager…", forget_window=True)

    @app.post("/label")
    async def label(req: LabelRequest) -> dict[str, Any]:
        """« C'était où ? » : ajoute la capture au jeu de test avec le pays réel."""
        return await engine.label(req)

    @app.post("/label/preview")
    async def label_preview(req: TruthRequest) -> dict[str, Any]:
        """Ce que dit le lien collé dans « C'était où ? » (pays, région, position), avant d'enregistrer."""
        return await engine.truth(req.link)

    @app.post("/metas/judge")
    async def judge(req: JudgeRequest) -> dict[str, Any]:
        """Le joueur confirme (« Juste ») ou écarte (« Faux ») un indice de l'amorce."""
        return await engine.judge(req)

    @app.post("/plonkit/refresh")
    async def plonkit_refresh() -> dict[str, Any]:
        """Bouton « Mettre à jour » : contrôle la liste des guides maintenant, sans attendre refresh_days."""
        if not engine.cfg.plonkit.enabled:
            raise HTTPException(409, "Plonk It désactivé dans la configuration")
        if not engine.schedule_plonkit(check=True):
            raise HTTPException(409, "mise à jour déjà en cours")
        return {"ok": True}

    @app.get("/map/countries")
    async def map_countries() -> JSONResponse:
        """Contours des pays (Natural Earth 1:50m, domaine public), avec leur seul code ISO."""
        if engine.borders is None:
            engine.borders = await asyncio.to_thread(Borders)
        return JSONResponse(engine.borders.geojson, headers={"Cache-Control": "max-age=86400"})

    @app.get("/settings")
    async def get_settings() -> dict[str, Any]:
        return current(engine.cfg)

    @app.get("/settings/file-only")
    async def get_file_only() -> dict[str, Any]:
        """Réglages réservés au fichier (sécurité), affichés en lecture seule avec leur raison."""
        return file_only(engine.cfg)

    @app.post("/settings")
    async def post_settings(changes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return await engine.apply_settings(changes)

    @app.get("/models")
    async def models() -> dict[str, Any]:
        try:
            return {"models": await engine.vision.list_models()}
        except VisionError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/models/test")
    async def test_model(req: ModelTestRequest) -> dict[str, Any]:
        """Le modèle accepte-t-il les images, et en combien de temps répond-il ?"""
        try:
            return {"ok": True, "seconds": round(await engine.vision.probe(req.model), 1)}
        except VisionError as exc:
            return {"ok": False, "error": str(exc)[:300]}

    @app.get("/storage")
    async def get_storage() -> dict[str, Any]:
        """Ce que le coach garde sur le disque, et la taille de chaque élément."""
        return await asyncio.to_thread(engine.storage_items)

    @app.post("/storage/clear")
    async def clear_storage(req: ClearRequest) -> dict[str, Any]:
        return await engine.clear_storage(req.id)

    @app.get("/progress")
    async def get_progress() -> dict[str, Any]:
        return await engine.progress()

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        if websocket.headers.get("origin") not in allowed:
            await websocket.close(code=1008)  # violation de politique
            return
        await websocket.accept()
        engine.clients.add(websocket)
        try:
            await websocket.send_json(engine.state())
            while True:
                await websocket.receive_text()  # l'interface n'envoie rien pour l'instant
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
