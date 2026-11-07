"""Verrous dans le moteur : ce que le coach verrouille d'après les marques, ce que le joueur pose ou rejette.

Engine hérite de LocksMixin (comme de MarksMixin) ; les verrous vivent dans l'entrée de la capture
(self.recent[id]["locks"]) : une nouvelle capture repart de zéro. Flux :
- _verdict (marks_engine) → coach_locks : pays certain, région d'un point net, ville proposée ;
- set_lock / reject_lock (routes) → position, région et ville proposée recalculées sous tes choix (la conclusion
  des marques, elle, reste indépendante : elle confirme ou contredit ce que tu as dit) ;
- publish_locks : message « locks » à l'interface, journal (mode débogage), astuces du pays verrouillé.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .evidence import Evidence, Verdict, as_dict
from .locate import haversine
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
        """Tes choix ont changé : position, région et ville proposée sont recalculées (la conclusion des marques,
        elle, n'en dépend pas), puis les verrous publiés."""
        entry = self.recent.get(capture_id)
        if entry is None:
            return
        if any(m.get("status") == "done" for m in entry["marks"]):
            await self._verdict(capture_id)  # publie les verrous
        else:
            await self.publish_locks(capture_id)

    # --- coach ------------------------------------------------------------------------------------
    async def coach_locks(self, capture_id: str, v: Verdict, cited: list[tuple[int, list[Evidence]]],
                          location: dict[str, Any] | None, target: str) -> None:
        """Après chaque conclusion : ce que le coach verrouille, et la ville qu'il propose.

        cited : preuves des marques qui situent la vue (sous tes choix) ; target : ton pays, sinon celui des marques.
        """
        entry = self.recent.get(capture_id)
        if entry is None or not self.cfg.locks.enabled:
            return
        country, region, proposal, read_regions = await asyncio.to_thread(self._candidates, v, cited, location, target)
        entry["read_regions"] = read_regions
        self.locks_of(entry).coach(country, region, proposal)
        await self.publish_locks(capture_id)

    def _candidates(self, v: Verdict, cited: list[tuple[int, list[Evidence]]], location: dict[str, Any] | None,
                    target: str) -> tuple[Lock | None, Lock | None, Lock | None, list[dict[str, Any]]]:
        """(pays certain, région, ville proposée, régions des lieux lus) d'après les marques."""
        lc, places = self.cfg.locks, self.places
        marks = ", ".join(str(c["n"]) for c in v.cites)
        country = Lock("country", v.country, why=f"marques {marks}") \
            if lc.auto_country and v.country and v.level == "certain" else None
        if not target:
            return country, None, None, []
        # Position nette : un point, ou « à moins de N km de ce lieu » quand N est petit (distances incohérentes, mais
        # la plus courte reste toujours vraie : Glamsbjerg 3 km sur le panneau danois du 2026-11-07).
        point = location if location and (location.get("kind") == "point" or (
            location.get("kind") == "rough" and location["radius_km"] <= lc.region_radius_km)) else None
        region = None
        if lc.auto_region and places and point:
            near = places.around(point["lat"], point["lon"], lc.region_radius_km, target)
            codes = {r for _, _, r, *_ in near if r}  # un lieu sans région connue ne contredit rien (Mordovie)
            if len(codes) == 1:  # tous les lieux autour du point : la même région
                code = codes.pop()
                region = Lock("region", target, region=code, name=places.region_name(code),
                              why="position estimée d'après tes marques")
        # Régions des lieux lus (homonyme retenu dans le pays) : proposées en un clic, surtout quand elles divergent
        # (« Oker » en Basse-Saxe, « Retz » → Rötz en Bavière, 2026-11-07).
        read: dict[str, tuple[int, list[Any]]] = {}
        for n, found in cited:
            for e in found:
                p = next((q for q in e.points if q[2] == target), None) if e.kind == "lieu" else None
                if p is not None:
                    read.setdefault(p[3], (n, p))
        by_region: dict[str, list[tuple[int, str, float, float]]] = {}
        for name, (n, p) in read.items():
            by_region.setdefault(p[4] if len(p) > 4 else "", []).append((n, name, p[0], p[1]))
        read_regions = [{"code": code, "name": places.region_name(code) if places else code,
                         "marks": sorted({n for n, *_ in items}), "places": sorted({name for _, name, *_ in items})}
                        for code, items in sorted(by_region.items(), key=lambda kv: -len(kv[1])) if code]
        # Sans point net : au moins deux lieux lus, tous dans la même région et proches les uns des autres (un lieu
        # seul ne suffit pas : un panneau nomme souvent une ville de la région voisine).
        # Avec un point net mais une limite de région toute proche, c'est le point qui dit vrai : pas de région.
        if point is None and lc.auto_region and len(by_region) == 1 and read_regions:
            items = by_region[read_regions[0]["code"]]
            spread = max((haversine(a[2:], b[2:]) for a in items for b in items), default=0.0)
            if len(items) >= 2 and spread <= lc.region_places_km:
                cited_marks = " ".join(f"{n}" for n in read_regions[0]["marks"])
                region = Lock("region", target, region=read_regions[0]["code"], name=read_regions[0]["name"],
                              why=f"lieux lus dans la même région (marques {cited_marks})")
        proposal = None
        if lc.propose_city:
            # Un lieu lu SANS distance (panneau d'entrée, enseigne) : on y est sans doute ; avec distance, non.
            bare = {(p[3], p[4] if len(p) > 4 else "", p[0], p[1])
                    for _, found in cited for e in found
                    if e.kind == "lieu" and e.km is None
                    for p in e.points[:1] if p[2] == target and len(p) > 3}
            if len(bare) == 1:
                name, code, lat, lon = bare.pop()
                proposal = Lock("city", target, region=code, name=name, lat=lat, lon=lon, why="lu sans distance")
            elif not bare and places and point:
                near = places.around(point["lat"], point["lon"], max(2.0, point["radius_km"]), target)
                if near:
                    _, name, code, lat, lon = near[0]
                    proposal = Lock("city", target, region=code, name=name, lat=lat, lon=lon,
                                    why="le plus proche de la position estimée")
        return country, region, proposal, read_regions

    # --- diffusion --------------------------------------------------------------------------------
    async def publish_locks(self, capture_id: str) -> None:
        entry = self.recent.get(capture_id)
        if entry is None or "locks" not in entry:
            return
        locks: Locks = entry["locks"]
        await self._log(capture_id, locks={**locks.as_dict(), "events": list(locks.events)})
        region = locks.held.get("region")
        bounds = await asyncio.to_thread(self.places.region_bounds, region.region) if region and self.places else None
        await self.broadcast({"type": "locks", "id": capture_id, **locks.as_dict(),
                              "read_regions": entry.get("read_regions", []), "region_bounds": bounds})
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
    async def reread_marks(self, capture_id: str) -> None:
        """Relit les marques lues (villages du pays arrivés) puis refait la conclusion."""
        entry = self.recent.get(capture_id)
        if entry is None:
            return
        done = [m for m in entry["marks"] if m.get("status") == "done"]
        for mark in done:
            mark["evidence"] = as_dict(await asyncio.to_thread(self.evidence_of, mark["text"]))
            await self.broadcast({"type": "mark", "id": capture_id, "n": mark["n"], "status": "done",
                                  "evidence": mark["evidence"]})
        if done:
            await self._verdict(capture_id)
