"""Marques et règles locales du moteur : vue figée, lecture des marques, conclusion, noms de lieux.

Sorti de server.py (2026-11-07, revue de code : le fichier dépassait 1 100 lignes). Engine hérite de MarksMixin ;
les attributs utilisés ici (cfg, recent, places, vision, background…) sont créés par Engine.__init__.
Flux : freeze (vue figée) → add_marks (découpe agrandie) → _read_mark (transcription par l'IA) → evidence_of
(règles locales) → _verdict (conclusion, position, villages du pays en tête via ensure_detail).
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import suppress
from dataclasses import asdict, dataclass
from typing import Any

from fastapi import HTTPException
from PIL import Image

from . import storage
from .capture import data_url, new_id, save_png
from .evidence import Evidence, Verdict, as_dict, from_dict, text_evidence, verdict
from .locate import keep_nearby, locate
from .locks import NO_SCOPE, Scope, restrict
from .marks import MAX_PER_ANALYSIS, DeleteRequest, FrameRequest, MarksRequest, crop_mark, reading
from .places import DB_NAME as PLACES_DB
from .places import COUNTRY, OLD_DBS, VERSION, Places, PlacesError, detail_name
from .places import build as build_places
from .vision import VisionError

FROZEN_FRAMES = 3  # vues figées en attente de marques
MARK_THUMB_SIDE = 360


@dataclass
class Conclusion:
    verdict: Verdict
    result: dict[str, Any]  # message « verdict » : conclusion, position, homonymes écartés, lieux hors de tes choix
    target: str  # pays où situer la vue : le tien s'il y en a un, sinon celui des marques
    cited: list[tuple[int, list[Evidence]]]  # preuves qui situent la vue (sous tes choix)


def conclude(done: list[tuple[int, list[dict[str, Any]]]], scores: list[tuple[str, float]], rules: Any,
             scope: Scope = NO_SCOPE) -> Conclusion:
    """Conclusion des marques lues (numéro, preuves), sans réseau : utilisée par le moteur ET par le banc (bench.py),
    pour que le banc mesure exactement ce que fait le coach.

    La conclusion (pays, certitude) ne tient PAS compte de tes choix ni de tes rejets (décidé avec l'utilisateur le
    2026-11-07) : elle confirme ou contredit ce que tu as dit, au lieu d'en être l'écho. Tes choix (scope)
    restreignent seulement la suite : homonymes retenus pour la position, région, ville proposée.
    """
    spread = rules.place_max_spread_km
    read, ignored = keep_nearby([(n, from_dict(ev)) for n, ev in done], spread)
    v = verdict(read, dict(scores), rules.prior_min)
    result = asdict(v)
    result["ignored"] = ignored  # homonymes lointains écartés
    # Position estimée, dans ton pays s'il y en a un (et ses homonymes seulement), sinon dans celui des marques :
    # lieux des marques qui le prouvent, et distances d'un panneau directionnel.
    target = scope[0] or v.country
    near = read
    if scope != NO_SCOPE:
        near, _ = keep_nearby([(n, restrict(from_dict(ev), scope)) for n, ev in done], spread)
    cited = {n for n, _ in near} if scope[0] else {c["n"] for c in v.cites}
    places = [(n, e) for n, found in near if n in cited for e in found if e.kind == "lieu" and target in e.countries]
    result["location"] = locate(places, target) if places else None
    # Lieux lus que tes choix écartent (« ③ Rötz » hors de ta Basse-Saxe) : grisés sur la carte, jamais effacés.
    kept = {(n, e.value) for n, found in near for e in found if e.kind == "lieu" and e.points}
    result["outside"] = [{"n": n, "name": e.value, "label": e.points[0][3], "lat": e.points[0][0],
                          "lon": e.points[0][1]}
                         for n, found in read for e in found
                         if scope != NO_SCOPE and e.kind == "lieu" and e.points and len(e.points[0]) > 3
                         and (n, e.value) not in kept]
    return Conclusion(v, result, target, [(n, f) for n, f in near if n in cited])


class MarksMixin:
    # --- marques -------------------------------------------------------------------------------
    async def freeze(self) -> dict[str, Any]:
        """Fige la vue : la fenêtre des marques l'affiche en plein écran pour y entourer des indices.

        Les marques complètent la manche en cours : il faut une capture d'abord (elle ouvre la manche).
        """
        if not self.cfg.marks.enabled:
            return {"ok": False, "error": "marques désactivées dans les réglages"}
        target = self.last_id if self.last_id in self.recent else None
        if target is None:
            error = "fais d'abord une capture : les marques complètent l'analyse d'une manche"
            await asyncio.to_thread(self.notifier.send, "Aucune analyse à compléter", error, error=True)
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
            raise HTTPException(404, "vue figée trop ancienne ou inconnue")
        frame = frozen[0]
        return {"image": data_url(frame, side=max(frame.size), quality=90), "width": frame.width,
                "height": frame.height}

    async def add_marks(self, req: MarksRequest) -> dict[str, Any]:
        """Découpe chaque marque dans la vue figée, l'agrandit si besoin et la fait transcrire."""
        mc = self.cfg.marks
        if not mc.enabled:
            raise HTTPException(409, "marques désactivées dans les réglages")
        if len(req.rects) > mc.max_marks:
            raise HTTPException(422, f"au plus {mc.max_marks} marques par vue figée")
        frozen = self.frozen.get(req.id)
        if frozen is None:
            raise HTTPException(404, "vue figée trop ancienne ou inconnue")
        frame, target = frozen
        entry = self.recent.get(target)
        if entry is None:
            raise HTTPException(409, "l'analyse de cette manche est trop ancienne : refais une capture")
        if len(entry["marks"]) + len(req.rects) > MAX_PER_ANALYSIS:
            raise HTTPException(422, f"au plus {MAX_PER_ANALYSIS} marques par manche")
        del self.frozen[req.id]  # une vue figée ne sert qu'une fois
        numbers = []
        for rect in req.rects:
            img, scale = await asyncio.to_thread(crop_mark, frame, rect, mc.upscale_to_px, mc.max_upscale)
            n = max((m["n"] for m in entry["marks"]), default=0) + 1  # une marque retirée garde son numéro
            mark = {"n": n, "rect": rect, "scale": round(scale, 2), "size": list(img.size), "status": "pending"}
            entry["marks"].append(mark)
            numbers.append(n)
            await self.broadcast({
                "type": "mark", "id": target, "n": n, "status": "pending", "scale": mark["scale"],
                "thumbnail": await asyncio.to_thread(data_url, img, MARK_THUMB_SIDE, 88),
            })
            if self.cfg.debug.enabled and entry.get("log") is not None:
                with suppress(OSError):  # découpe gardée pour mesurer la lecture après coup
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
            mark.update(status="error", error="modèle de vision désactivé")
        else:
            async with self.mark_slots:
                try:
                    fiche, seconds = await self.vision.ask(img, mc.prompt, mc.model or self.cfg.vision.model,
                                                           mc.max_tokens)
                    mark.update(status="done", seconds=round(seconds, 1), **reading(fiche))
                    mark["evidence"] = as_dict(await asyncio.to_thread(self.evidence_of, mark["text"]))
                except VisionError as exc:
                    mark.update(status="error", error=str(exc)[:300])
        entry = self.recent.get(capture_id)
        if entry is None or not any(m is mark for m in entry["marks"]):
            return  # retirée pendant la lecture (ou manche oubliée) : elle ne doit pas réapparaître
        message.update({k: v for k, v in mark.items() if k not in ("n", "rect", "size")})
        await self._log_marks(capture_id)
        await self.broadcast(message)
        await self._verdict(capture_id)

    def evidence_of(self, lines: list[str]) -> list[Evidence]:
        """Preuves tirées du texte d'une marque, selon les règles actives (appelée hors de la boucle).

        Jamais restreintes par tes choix (« c'est sûr ») : la conclusion des marques reste un avis indépendant.
        """
        rc = self.cfg.rules
        found = [e for e in text_evidence(lines)
                 if (e.kind == "alphabet" and rc.scripts) or (e.kind in ("lettres", "mot") and rc.letters)]
        if rc.places and self.places is not None:
            found += self.places.match(lines, rc.place_min_len)
        # Seuls les pays candidats comptent (la Moldavie n'empêche pas « ș » de désigner la Roumanie). Une preuve qui
        # ne désigne que des pays hors liste reste affichée, mais ne compte pas (« Manto » → Honduras, 2026-11-07).
        known = set(self.cfg.streetclip.countries.values())
        for e in found:
            kept = [c for c in e.countries if c in known]
            if e.countries and not kept:
                e.note = f"hors de tes pays candidats ({', '.join(e.countries[:4])})"
            e.countries = kept
        return found

    async def _verdict(self, capture_id: str) -> None:
        """Conclusion des marques lues (conclude), recalculée à chaque lecture, retrait ou choix, poussée à
        l'interface ; puis ce que le coach verrouille."""
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
        """Le joueur retire une marque (lecture fausse) : elle ne compte plus, les autres gardent leur numéro."""
        entry = self.recent.get(req.id)
        if entry is None:
            raise HTTPException(404, "analyse trop ancienne ou inconnue")
        before = len(entry["marks"])
        entry["marks"] = [m for m in entry["marks"] if m["n"] != req.n]
        if len(entry["marks"]) == before:
            raise HTTPException(404, "marque inconnue")
        await self._log_marks(req.id)
        await self.broadcast({"type": "mark_removed", "id": req.id, "n": req.n})
        await self._verdict(req.id)
        return {"ok": True}

    async def _log_marks(self, capture_id: str) -> None:
        entry = self.recent.get(capture_id)
        if entry is not None:  # copie : le journal s'écrit dans un thread pendant que les lectures arrivent
            await self._log(capture_id, marks=[dict(m) for m in entry["marks"]])


    # --- noms de lieux (GeoNames) ----------------------------------------------------------------
    def schedule_places(self) -> None:
        if self.places_task and not self.places_task.done():
            return
        self.places_task = asyncio.create_task(self.load_places())

    async def load_places(self) -> None:
        """Ouvre l'index des lieux ; le télécharge et le construit d'abord s'il manque (une fois, ~11 Mo)."""
        rc = self.cfg.rules
        path = rc.places_path / PLACES_DB
        for old in OLD_DBS:  # anciens formats, remplacés (l'archive gardée évite de retélécharger)
            (rc.places_path / old).unlink(missing_ok=True)
        for old in rc.places_path.glob("detail-*.sqlite"):
            if not old.name.endswith(f"-{VERSION}.sqlite"):
                old.unlink(missing_ok=True)
        try:
            if not path.exists():
                self.places_message = "téléchargement du répertoire GeoNames (~11 Mo)…"
                await self.broadcast(self.state())
                await asyncio.to_thread(build_places, rc.places_url, rc.places_path, regions_url=rc.regions_url)
            places = await asyncio.to_thread(Places, path)
            for detail in sorted(rc.places_path.glob(f"detail-*-{VERSION}.sqlite")):  # pays déjà détaillés
                await asyncio.to_thread(places.add_detail, detail.name.split("-")[1], detail)
            self.places = places
            self.places_message = self._places_summary()
        except (PlacesError, OSError, sqlite3.Error) as exc:  # hors ligne, disque… : les autres règles restent
            self.places, self.places_message = None, f"indisponible : {exc}"[:300]
        await self.broadcast(self.state())

    def _places_summary(self) -> str:
        if self.places is None:
            return self.places_message
        details = ", ".join(sorted(self.places.details))
        return f"{self.places.count} noms de lieux (GeoNames, CC BY 4.0)" + (f" ; villages : {details}" if details else "")

    def ensure_detail(self, country: str) -> None:
        """Répertoire complet du pays en tête (villages), une fois : puis les marques sont relues avec lui."""
        if not (self.cfg.rules.places and self.cfg.rules.detail and self.places) or not COUNTRY.fullmatch(country):
            return
        if country in self.places.details:  # déjà là : il devient le plus récemment utilisé
            storage.touch(self.cfg.rules.places_path / detail_name(country))
            return
        if country in self.detail_failed or (country in self.detail_tasks and not self.detail_tasks[country].done()):
            return
        self.detail_tasks[country] = asyncio.create_task(self._load_detail(country))

    async def _load_detail(self, country: str) -> None:
        rc, places = self.cfg.rules, self.places
        if places is None:
            return
        self.places_message = f"{self._places_summary()} ; téléchargement des villages ({country})…"
        await self.broadcast(self.state())
        try:
            path = await asyncio.to_thread(
                build_places, rc.detail_url.format(country), rc.places_path, db_name=detail_name(country),
                archive_name=None, populated_only=True)
            await asyncio.to_thread(places.add_detail, country, path)
        except (PlacesError, OSError, sqlite3.Error) as exc:
            self.detail_failed.add(country)
            self.places_message = f"{self._places_summary()} ; villages ({country}) indisponibles : {exc}"[:300]
            await self.broadcast(self.state())
            return
        await self.evict_caches(keep={country})
        self.places_message = self._places_summary()
        await self.broadcast(self.state())
        for capture_id in list(self.recent):  # relire les marques avec les villages
            await self.reread_marks(capture_id)
