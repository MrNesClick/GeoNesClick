"""Verrous dans le moteur : ce que le coach verrouille d'après les marques, ce que le joueur pose ou rejette.

Engine hérite de LocksMixin (comme de MarksMixin) ; les verrous vivent dans l'entrée de la capture
(self.recent[id]["locks"]) : une nouvelle capture repart de zéro. Flux :
- _verdict (marks_engine) → coach_locks : pays certain, région d'un point net, ville proposée ;
- set_lock / reject_lock (routes) → les marques sont relues sous la nouvelle restriction, puis la conclusion ;
- publish_locks : message « locks » à l'interface, journal (mode débogage), astuces du pays verrouillé.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .evidence import Evidence, Verdict, as_dict
from .locks import NO_SCOPE, Lock, Locks, Scope

CODE = r"^[A-Z]{2}$"
REGION_CODE = r"^$|^[A-Z]{2}\.[0-9A-Z]{1,20}$"
SAME_PLACE_DEG = 0.01  # une ville choisie dans la recherche : mêmes coordonnées que dans l'index, à ~1 km près


class LockRequest(BaseModel):
    """Verrou posé par le joueur : pays, région ou ville trouvée par /locks/search (vérifiée dans l'index)."""

    id: str = Field(max_length=32)
    level: Literal["country", "region", "city"]
    country: str = Field(pattern=CODE)
    region: str = Field(default="", max_length=24, pattern=REGION_CODE)
    name: str = Field(default="", max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class RejectRequest(BaseModel):
    id: str = Field(max_length=32)
    level: Literal["country", "region", "city", "proposal"]


class PlaceSearchRequest(BaseModel):
    level: Literal["region", "city"]
    q: str = Field(default="", max_length=100)
    country: str = Field(pattern=CODE)
    region: str = Field(default="", max_length=24, pattern=REGION_CODE)


class LocksMixin:
    # --- état -------------------------------------------------------------------------------------
    @staticmethod
    def locks_of(entry: dict[str, Any]) -> Locks:
        return entry.setdefault("locks", Locks())

    def lock_scope(self, capture_id: str) -> Scope:
        """Restriction des preuves des marques pour cette capture (verrous du joueur, rejets)."""
        entry = self.recent.get(capture_id)
        if not (self.cfg.locks.enabled and entry and "locks" in entry):
            return NO_SCOPE
        return entry["locks"].scope()

    def _entry(self, capture_id: str) -> dict[str, Any]:
        if not self.cfg.locks.enabled:
            raise HTTPException(409, "verrous désactivés dans les réglages")
        entry = self.recent.get(capture_id)
        if entry is None:
            raise HTTPException(404, "capture trop ancienne ou inconnue")
        return entry

    # --- joueur -----------------------------------------------------------------------------------
    async def set_lock(self, req: LockRequest) -> dict[str, Any]:
        entry = self._entry(req.id)
        if req.country not in set(self.cfg.streetclip.countries.values()):
            raise HTTPException(422, "pays inconnu")
        region_name = ""
        if req.level == "country":
            lock = Lock("country", req.country)
        else:
            if self.places is None:
                raise HTTPException(409, "répertoire des lieux indisponible : verrouille le pays seulement")
            if req.level == "region":
                if not req.region.startswith(f"{req.country}."):
                    raise HTTPException(422, "région inconnue pour ce pays")
                lock = Lock("region", req.country, region=req.region,
                            name=await asyncio.to_thread(self.places.region_name, req.region))
            else:
                lock = await asyncio.to_thread(self._known_city, req)
                if lock.region:
                    region_name = await asyncio.to_thread(self.places.region_name, lock.region)
        self.locks_of(entry).lock(lock, region_name)
        await self._locks_changed(req.id)
        return {"ok": True}

    def _known_city(self, req: LockRequest) -> Lock:
        """La ville doit exister dans l'index (nom, pays, coordonnées) : on reprend ses valeurs, pas celles reçues."""
        if req.lat is None or req.lon is None or not req.name.strip():
            raise HTTPException(422, "ville incomplète")
        for country, _, name, lat, lon, region in self.places.lookup(req.name):
            if (country == req.country and abs(lat - req.lat) < SAME_PLACE_DEG
                    and abs(lon - req.lon) < SAME_PLACE_DEG and (not req.region or region == req.region)):
                return Lock("city", country, region=region, name=name, lat=lat, lon=lon)
        raise HTTPException(422, "ville inconnue du répertoire des lieux")

    async def reject_lock(self, req: RejectRequest) -> dict[str, Any]:
        entry = self._entry(req.id)
        try:
            self.locks_of(entry).reject(req.level)
        except KeyError as exc:
            raise HTTPException(404, "rien à rejeter à ce niveau") from exc
        await self._locks_changed(req.id)
        return {"ok": True}

    async def search_places(self, req: PlaceSearchRequest) -> dict[str, Any]:
        """Champ « + » du bandeau : régions du pays, ou villes du pays (et de la région), dans l'index LOCAL."""
        if not self.cfg.locks.enabled:
            raise HTTPException(409, "verrous désactivés dans les réglages")
        if self.places is None:
            raise HTTPException(409, "répertoire des lieux indisponible")
        if req.level == "region":
            return {"results": await asyncio.to_thread(self.places.regions, req.country, req.q)}
        return {"results": await asyncio.to_thread(self.places.search, req.q, req.country, req.region)}

    async def _locks_changed(self, capture_id: str) -> None:
        """La restriction a changé : les marques sont relues sous elle, puis la conclusion (qui publie les verrous)."""
        entry = self.recent.get(capture_id)
        if entry is None:
            return
        if not await self.reread_marks(capture_id):
            await self.publish_locks(capture_id)

    # --- coach ------------------------------------------------------------------------------------
    async def coach_locks(self, capture_id: str, v: Verdict, read: list[tuple[int, list[Evidence]]],
                          location: dict[str, Any] | None) -> None:
        """Après chaque conclusion : ce que le coach verrouille, et la ville qu'il propose."""
        entry = self.recent.get(capture_id)
        if entry is None or not self.cfg.locks.enabled:
            return
        country, region, proposal = await asyncio.to_thread(self._candidates, v, read, location)
        self.locks_of(entry).coach(country, region, proposal)
        await self.publish_locks(capture_id)

    def _candidates(self, v: Verdict, read: list[tuple[int, list[Evidence]]], location: dict[str, Any] | None
                    ) -> tuple[Lock | None, Lock | None, Lock | None]:
        lc, places = self.cfg.locks, self.places
        if not v.country:
            return None, None, None
        cites = ", ".join(str(c["n"]) for c in v.cites)
        country = Lock("country", v.country, why=f"marques {cites}") if lc.auto_country and v.level == "certain" \
            else None
        point = location if location and location.get("kind") == "point" else None
        region = None
        if lc.auto_region and places and point:
            near = places.around(point["lat"], point["lon"], lc.region_radius_km, v.country)
            codes = {r for _, _, r, *_ in near}
            if len(codes) == 1 and "" not in codes:  # tous les lieux autour du point : la même région
                code = codes.pop()
                region = Lock("region", v.country, region=code, name=places.region_name(code),
                              why=f"position estimée (marques {cites})")
        proposal = None
        if lc.propose_city:
            # Un lieu lu SANS distance (panneau d'entrée, enseigne) : on y est sans doute ; avec distance, non.
            cited = {c["n"] for c in v.cites}
            bare = {(p[3], p[4] if len(p) > 4 else "", p[0], p[1])
                    for n, found in read if n in cited for e in found
                    if e.kind == "lieu" and e.km is None
                    for p in e.points[:1] if p[2] == v.country and len(p) > 3}
            if len(bare) == 1:
                name, code, lat, lon = bare.pop()
                proposal = Lock("city", v.country, region=code, name=name, lat=lat, lon=lon, why="lu sans distance")
            elif not bare and places and point:
                near = places.around(point["lat"], point["lon"], max(2.0, point["radius_km"]), v.country)
                if near:
                    _, name, code, lat, lon = near[0]
                    proposal = Lock("city", v.country, region=code, name=name, lat=lat, lon=lon,
                                    why="le plus proche de la position estimée")
        return country, region, proposal

    # --- diffusion --------------------------------------------------------------------------------
    async def publish_locks(self, capture_id: str) -> None:
        entry = self.recent.get(capture_id)
        if entry is None or "locks" not in entry:
            return
        locks: Locks = entry["locks"]
        await self._log(capture_id, locks={**locks.as_dict(), "events": list(locks.events)})
        await self.broadcast({"type": "locks", "id": capture_id, **locks.as_dict()})
        country = locks.country()
        if country and country not in entry.setdefault("tips_for", set()):
            await self._tips_for(capture_id, country)

    async def _tips_for(self, capture_id: str, country: str) -> None:
        """Astuces Plonk It du pays verrouillé, même s'il n'était pas parmi les pays candidats de StreetCLIP."""
        entry = self.recent.get(capture_id)
        if entry is None or entry.get("emb") is None:
            return
        entry["tips_for"].add(country)
        similar = await asyncio.to_thread(self.similar, entry["emb"], [], [country])
        if not similar:
            return
        lang = self.translation_lang
        missing = list({t["id"]: t["text"] for tips in similar.values() for t in tips if t["translated"] is None}
                       .items())
        # batches : un message « tips_translated » de plus à attendre (l'interface compte les lots).
        await self.broadcast({"type": "similar", "id": capture_id, "similar": similar,
                              "batches": 1 if lang and missing else 0})
        if lang and missing:
            task = asyncio.create_task(self._translate_tips(capture_id, missing, lang))
            self.background.add(task)
            task.add_done_callback(self.background.discard)

    # --- relecture des marques ---------------------------------------------------------------------
    async def reread_marks(self, capture_id: str) -> bool:
        """Relit les marques lues (villages arrivés, restriction changée) puis refait la conclusion.

        False s'il n'y avait aucune marque lue (rien n'a été recalculé).
        """
        entry = self.recent.get(capture_id)
        if entry is None:
            return False
        done = [m for m in entry["marks"] if m.get("status") == "done"]
        scope = self.lock_scope(capture_id)
        for mark in done:
            mark["evidence"] = as_dict(await asyncio.to_thread(self.evidence_of, mark["text"], scope))
            await self.broadcast({"type": "mark", "id": capture_id, "n": mark["n"], "status": "done",
                                  "evidence": mark["evidence"]})
        if done:
            await self._verdict(capture_id)
        return bool(done)
