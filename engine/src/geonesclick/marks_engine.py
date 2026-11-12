"""Marks and local rules of the engine: frozen view, mark reading, conclusion, place names.

Split out of server.py (the file was over 1,100 lines). Engine inherits from MarksMixin;
the attributes used here (cfg, recent, places, vision, background…) are created by Engine.__init__.
Flow: freeze (frozen view) → add_marks (enlarged crop) → _read_mark (transcription by the AI) → evidence_of
(local rules) → _verdict (conclusion, position, villages of the leading country via ensure_detail).
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import HTTPException
from PIL import Image

from .i18n import t
from . import storage
from .capture import data_url, new_id, save_png
from .evidence import Evidence, Verdict, as_dict, from_dict, text_evidence, verdict
from .locate import keep_nearby, locate
from .locks import NO_SCOPE, Scope, restrict
from .marks import MAX_PER_ANALYSIS, DeleteRequest, FrameRequest, MarksRequest, crop_mark, reading
from .places import DB_NAME as PLACES_DB
from .places import COUNTRY, OLD_DBS, VERSION, Places, PlacesError, detail_name
from .places import build as build_places
from .vision import with_language, VisionError

FROZEN_FRAMES = 3  # frozen views waiting for marks
MARK_THUMB_SIDE = 360


@dataclass
class Conclusion:
    verdict: Verdict
    result: dict[str, Any]  # "verdict" message: conclusion, position, namesakes ruled out, places outside your choices
    target: str  # country in which to locate the view: yours if there is one, otherwise the marks' one
    cited: list[tuple[int, list[Evidence]]]  # proofs that locate the view (under your choices)


def conclude(done: list[tuple[int, list[dict[str, Any]]]], scores: list[tuple[str, float]], rules: Any,
             scope: Scope = NO_SCOPE) -> Conclusion:
    """Conclusion of the marks read (number, proofs), offline: used by the engine AND by the bench (bench.py),
    so that the bench measures exactly what the coach does.

    The conclusion (country, certainty) does NOT take your choices or your rejections into account: it
    confirms or contradicts what you said, instead of echoing it. Your choices (scope)
    only narrow down what follows: namesakes kept for the position, region, suggested city.
    """
    spread = rules.place_max_spread_km
    read, ignored = keep_nearby([(n, from_dict(ev)) for n, ev in done], spread)
    v = verdict(read, dict(scores), rules.prior_min)
    result = asdict(v)
    result["ignored"] = ignored  # distant namesakes ruled out
    # Estimated position, in your country if there is one (and its namesakes only), otherwise in the marks' one:
    # places of the marks that prove it, and a direction sign's distances.
    target = scope[0] or v.country
    near = read
    if scope != NO_SCOPE:
        near, _ = keep_nearby([(n, restrict(from_dict(ev), scope)) for n, ev in done], spread)
    cited = {n for n, _ in near} if scope[0] else {c["n"] for c in v.cites}
    places = [(n, e) for n, found in near if n in cited for e in found if e.kind == "place" and target in e.countries]
    result["location"] = locate(places, target) if places else None
    # Places read that your choices rule out ("③ Rötz" outside your Lower Saxony): greyed out on the map, never erased.
    kept = {(n, e.value) for n, found in near for e in found if e.kind == "place" and e.points}
    result["outside"] = [{"n": n, "name": e.value, "label": e.points[0][3], "lat": e.points[0][0],
                          "lon": e.points[0][1]}
                         for n, found in read for e in found
                         if scope != NO_SCOPE and e.kind == "place" and e.points and len(e.points[0]) > 3
                         and (n, e.value) not in kept]
    return Conclusion(v, result, target, [(n, f) for n, f in near if n in cited])


class MarksMixin:
    # --- marks ---------------------------------------------------------------------------------
    async def freeze(self) -> dict[str, Any]:
        """Freezes the view: the marks window shows it in full screen to draw a box around clues.

        The marks complete the current round: a capture is needed first (it opens the round).
        """
        if not self.cfg.marks.enabled:
            return {"ok": False, "error": t("marks.off")}
        target = self.last_id if self.last_id in self.recent else None
        if target is None:
            error = t("marks.capture_first")
            await asyncio.to_thread(self.notifier.send, t("marks.nothing_to_complete"), error, error=True)
            await self.broadcast({"type": "error", "message": error[0].upper() + error[1:] + "."})
            return {"ok": False, "error": error}
        frame, error = await self._grab()
        if frame is None:
            return {"ok": False, "error": error}
        freeze_id = new_id()
        self.frozen[freeze_id] = (frame, target)
        while len(self.frozen) > FROZEN_FRAMES:
            self.frozen.popitem(last=False)
        entry = self.recent[target]
        await self.broadcast({
            "type": "freeze", "id": freeze_id, "width": frame.width, "height": frame.height,
            "target": target, "target_at": entry["at"], "marks": len(entry["marks"]),
        })
        return {"ok": True, "id": freeze_id}

    def frozen_image(self, req: FrameRequest) -> dict[str, Any]:
        frozen = self.frozen.get(req.id)
        if frozen is None:
            raise HTTPException(404, t("marks.frozen_unknown"))
        frame = frozen[0]
        return {"image": data_url(frame, side=max(frame.size), quality=90), "width": frame.width,
                "height": frame.height}

    async def add_marks(self, req: MarksRequest) -> dict[str, Any]:
        """Crops each mark from the frozen view, enlarges it if needed and has it transcribed."""
        mc = self.cfg.marks
        if not mc.enabled:
            raise HTTPException(409, t("marks.off"))
        if len(req.rects) > mc.max_marks:
            raise HTTPException(422, t("marks.too_many_frozen", n=mc.max_marks))
        frozen = self.frozen.get(req.id)
        if frozen is None:
            raise HTTPException(404, t("marks.frozen_unknown"))
        frame, target = frozen
        entry = self.recent.get(target)
        if entry is None:
            raise HTTPException(409, t("marks.analysis_too_old"))
        if len(entry["marks"]) + len(req.rects) > MAX_PER_ANALYSIS:
            raise HTTPException(422, t("marks.too_many_round", n=MAX_PER_ANALYSIS))
        del self.frozen[req.id]  # a frozen view is only used once
        numbers = []
        for rect in req.rects:
            img, scale = await asyncio.to_thread(crop_mark, frame, rect, mc.upscale_to_px, mc.max_upscale)
            n = max((m["n"] for m in entry["marks"]), default=0) + 1  # a removed mark keeps its number
            mark = {"n": n, "rect": rect, "scale": round(scale, 2), "size": list(img.size), "status": "pending"}
            entry["marks"].append(mark)
            numbers.append(n)
            await self.broadcast({
                "type": "mark", "id": target, "n": n, "status": "pending", "scale": mark["scale"],
                "thumbnail": await asyncio.to_thread(data_url, img, MARK_THUMB_SIDE, 88),
            })
            if self.cfg.debug.enabled and entry.get("log") is not None:
                with suppress(OSError):  # crop kept to measure the reading afterwards
                    await asyncio.to_thread(save_png, img, self.cfg.capture.path, f"mark-{target}-{n}")
            task = asyncio.create_task(self._read_mark(target, mark, img))
            self.background.add(task)
            task.add_done_callback(self.background.discard)
        await self._log_marks(target)
        return {"ok": True, "id": target, "marks": numbers}

    async def _read_mark(self, capture_id: str, mark: dict[str, Any], img: Image.Image) -> None:
        mc, n = self.cfg.marks, mark["n"]
        message: dict[str, Any] = {"type": "mark", "id": capture_id, "n": n}
        if not self.cfg.vision.enabled:
            mark.update(status="error", error=t("marks.vision_off"))
        else:
            async with self.mark_slots:
                try:
                    fiche, seconds = await self.vision.ask(img, with_language(mc.prompt), mc.model or self.cfg.vision.model,
                                                           mc.max_tokens)
                    mark.update(status="done", seconds=round(seconds, 1), **reading(fiche))
                    mark["evidence"] = as_dict(await asyncio.to_thread(self.evidence_of, mark["text"]))
                except VisionError as exc:
                    mark.update(status="error", error=str(exc)[:300])
        entry = self.recent.get(capture_id)
        if entry is None or not any(m is mark for m in entry["marks"]):
            return  # removed during the reading (or round forgotten): it must not reappear
        message.update({k: v for k, v in mark.items() if k not in ("n", "rect", "size")})
        await self._log_marks(capture_id)
        await self.broadcast(message)
        await self._verdict(capture_id)

    def evidence_of(self, lines: list[str]) -> list[Evidence]:
        """Proofs drawn from a mark's text, according to the active rules (called outside the loop).

        Never restricted by your choices ("it's certain"): the marks' conclusion stays an independent opinion.
        """
        rc = self.cfg.rules
        found = [e for e in text_evidence(lines)
                 if (e.kind == "alphabet" and rc.scripts) or (e.kind in ("letters", "word") and rc.letters)]
        if rc.places and self.places is not None:
            found += self.places.match(lines, rc.place_min_len)
        # Only the candidate countries count (Moldova does not prevent "ș" from pointing to Romania). A proof that
        # only points to countries outside the list stays visible, but does not count ("Manto" → Honduras).
        known = set(self.cfg.streetclip.countries.values())
        for e in found:
            kept = [c for c in e.countries if c in known]
            if e.countries and not kept:
                e.note = t("marks.outside_candidates", list=", ".join(e.countries[:4]))
            e.countries = kept
        return found

    async def _verdict(self, capture_id: str) -> None:
        """Conclusion of the marks read (conclude), recomputed on each reading, removal or choice, pushed to
        the UI; then what the coach locks."""
        entry = self.recent.get(capture_id)
        if entry is None:
            return
        done = [(m["n"], m.get("evidence", [])) for m in entry["marks"] if m.get("status") == "done"]
        c = await asyncio.to_thread(conclude, done, entry.get("scores") or [], self.cfg.rules,
                                    self.lock_scope(capture_id))
        v, result, target = c.verdict, c.result, c.target
        if target:
            self.ensure_detail(target)
        entry["verdict"] = result
        await self._log(capture_id, verdict=result)
        await self.broadcast({"type": "verdict", "id": capture_id, **result})
        await self.coach_locks(capture_id, v, c.cited, result["location"], target)

    async def remove_mark(self, req: DeleteRequest) -> dict[str, Any]:
        """The player removes a mark (wrong reading): it no longer counts, the others keep their number."""
        entry = self.recent.get(req.id)
        if entry is None:
            raise HTTPException(404, t("marks.analysis_unknown"))
        before = len(entry["marks"])
        entry["marks"] = [m for m in entry["marks"] if m["n"] != req.n]
        if len(entry["marks"]) == before:
            raise HTTPException(404, t("marks.unknown"))
        await self._log_marks(req.id)
        await self.broadcast({"type": "mark_removed", "id": req.id, "n": req.n})
        await self._verdict(req.id)
        return {"ok": True}

    async def _log_marks(self, capture_id: str) -> None:
        entry = self.recent.get(capture_id)
        if entry is not None:  # copy: the log is written in a thread while the readings arrive
            await self._log(capture_id, marks=[dict(m) for m in entry["marks"]])


    # --- place names (GeoNames) ------------------------------------------------------------------
    def schedule_places(self) -> None:
        if self.places_task and not self.places_task.done():
            return
        self.places_task = asyncio.create_task(self.load_places())

    async def load_places(self) -> None:
        """Opens the places index; downloads and builds it first if missing (once, ~11 MB)."""
        rc = self.cfg.rules
        path = rc.places_path / PLACES_DB
        for old in OLD_DBS:  # old formats, replaced (the kept archive avoids downloading again)
            (rc.places_path / old).unlink(missing_ok=True)
        for old in rc.places_path.glob("detail-*.sqlite"):
            if not old.name.endswith(f"-{VERSION}.sqlite"):
                old.unlink(missing_ok=True)
        try:
            if not path.exists():
                self.places_message = t("places.downloading")
                await self.broadcast(self.state())
                await asyncio.to_thread(build_places, rc.places_url, rc.places_path, regions_url=rc.regions_url)
            places = await asyncio.to_thread(Places, path)
            for detail in sorted(rc.places_path.glob(f"detail-*-{VERSION}.sqlite")):  # countries already detailed
                await asyncio.to_thread(places.add_detail, detail.name.split("-")[1], detail)
            self.places = places
            self.places_message = self._places_summary()
        except (PlacesError, OSError, sqlite3.Error) as exc:  # offline, disk…: the other rules remain
            self.places, self.places_message = None, t("srv.unavailable", error=exc)[:300]
        await self.broadcast(self.state())

    def _places_summary(self) -> str:
        if self.places is None:
            return self.places_message
        details = ", ".join(sorted(self.places.details))
        return t("places.summary", n=self.places.count, villages=t("places.summary_villages", list=details) if details else "")

    def ensure_detail(self, country: str) -> None:
        """Full directory of the leading country (villages), once: then the marks are re-read with it."""
        if not (self.cfg.rules.places and self.cfg.rules.detail and self.places) or not COUNTRY.fullmatch(country):
            return
        if country in self.places.details:  # already there: it becomes the most recently used
            storage.touch(self.cfg.rules.places_path / detail_name(country))
            return
        if country in self.detail_failed or (country in self.detail_tasks and not self.detail_tasks[country].done()):
            return
        self.detail_tasks[country] = asyncio.create_task(self._load_detail(country))

    async def _load_detail(self, country: str) -> None:
        rc, places = self.cfg.rules, self.places
        if places is None:
            return
        self.places_message = t("places.downloading_villages", summary=self._places_summary(), country=country)
        await self.broadcast(self.state())
        try:
            path = await asyncio.to_thread(
                build_places, rc.detail_url.format(country), rc.places_path, db_name=detail_name(country),
                archive_name=None, populated_only=True)
            await asyncio.to_thread(places.add_detail, country, path)
        except (PlacesError, OSError, sqlite3.Error) as exc:
            self.detail_failed.add(country)
            self.places_message = t("places.villages_unavailable", summary=self._places_summary(), country=country, error=exc)[:300]
            await self.broadcast(self.state())
            return
        await self.evict_caches(keep={country})
        self.places_message = self._places_summary()
        await self.broadcast(self.state())
        for capture_id in list(self.recent):  # re-read the marks with the villages
            await self.reread_marks(capture_id)
