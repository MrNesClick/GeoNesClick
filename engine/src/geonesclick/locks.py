"""Country › region › city locks: what is set for the current capture, and who set it.

Decided with the user on 2026-11-07 (OSINT approach: pin down what is certain, then narrow down):
- the COACH locks on its own the "certain" country and the region of a sharp point; a city, it only SUGGESTS
  (a "Pau 40 km" sign names a place where you are not); its locks follow the proofs (a removed mark
  can undo them);
- the HUMAN can always reject a lock (✕): the rejection lasts the whole capture, the coach does not lock the
  same thing again; they can also lock themselves, and the coach never replaces that lock;
- a human lock at one level brings along the levels above ("Orthez": France, Nouvelle-Aquitaine); a
  rejection takes away the levels below, which depended on it;
- everything is logged (debug mode) to measure the rules' errors;
- locks last one capture: a new capture starts from scratch (a stale lock would skew the next one).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any

from .i18n import t
from .evidence import Evidence
from .places import normalise

LEVELS = ("country", "region", "city")
Scope = tuple[str | None, str | None, set[str], set[str]]  # see Locks.scope
NO_SCOPE: Scope = (None, None, set(), set())


@dataclass
class Lock:
    level: str  # "country", "region" or "city"
    country: str  # 2-letter ISO code
    region: str = ""  # GeoNames code of the region ("FR.75"): region, and city if known
    name: str = ""  # region or city as displayed (the country: the UI has its name)
    lat: float | None = None  # city
    lon: float | None = None
    by: str = "coach"  # "coach" or "user"
    why: str = ""  # what made it be set (coach: the marks that prove it)

    def same(self, other: Lock) -> bool:
        """Same place at the same level, whoever the author."""
        if self.level != other.level or self.country != other.country:
            return False
        if self.level == "country":
            return True
        if self.level == "region":
            return self.region == other.region
        return normalise(self.name) == normalise(other.name) and self.region == other.region


@dataclass
class Locks:
    held: dict[str, Lock] = field(default_factory=dict)  # level → lock, in the order country, region, city
    rejected: list[Lock] = field(default_factory=list)
    proposal: Lock | None = None  # city suggested by the coach (one click to lock it)
    events: list[dict[str, Any]] = field(default_factory=list)

    # --- human ---------------------------------------------------------------------------------
    def lock(self, lock: Lock, region_name: str = "") -> None:
        """Lock set by the player (or accepted suggestion), with the levels above.

        region_name: name of a city's region (otherwise the one of the lock in place, or its code).
        """
        lock = replace(lock, by="user")
        chain = [lock]
        if lock.level in ("region", "city"):
            chain.insert(0, Lock("country", lock.country, by="user"))
        if lock.level == "city" and lock.region:
            held = self.held.get("region")
            name = region_name or (held.name if held and held.region == lock.region else lock.region)
            chain.insert(1, Lock("region", lock.country, region=lock.region, name=name, by="user"))
        for item in chain:
            self.rejected = [r for r in self.rejected if not r.same(item)]  # the player wins over their own rejection
            self._set(item)
        if self.proposal and lock.level == "city":
            self.proposal = None

    def reject(self, level: str) -> Lock:
        """✕ on a lock (or on the suggestion, level "proposal"): ruled out for the whole capture."""
        if level == "proposal":
            if self.proposal is None:
                raise KeyError(level)
            gone, self.proposal = self.proposal, None
        else:
            gone = self.held.pop(level)
            for below in LEVELS[LEVELS.index(level) + 1:]:
                self.held.pop(below, None)
        self.rejected.append(gone)
        self._drop_orphan_proposal()
        self._event("reject", gone)
        return gone

    # --- coach ---------------------------------------------------------------------------------
    def coach(self, country: Lock | None, region: Lock | None, proposal: Lock | None) -> None:
        """What the proofs allow now; the player's locks and rejections win."""
        for level, candidate in (("country", country), ("region", region)):
            held = self.held.get(level)
            if held and held.by == "user":
                continue
            parent = self.held.get("country")
            fits = candidate is not None and not self._rejected(candidate) and (
                level == "country" or (parent is not None and parent.country == candidate.country))
            if fits and not (held and held.same(candidate)):
                self._set(replace(candidate, by="coach"))
            elif not fits and held:
                self.held.pop(level)
                for below in LEVELS[LEVELS.index(level) + 1:]:
                    if below in self.held and self.held[below].by == "coach":
                        self.held.pop(below)
                self._event("unlock", held)
        self.proposal = None
        if proposal is not None and "city" not in self.held and not self._rejected(proposal) and self._fits(proposal):
            self.proposal = replace(proposal, by="coach")

    # --- what narrows down the search ----------------------------------------------------------
    def scope(self) -> tuple[str | None, str | None, set[str], set[str]]:
        """(locked country, locked region, rejected countries, rejected regions) to locate the view.

        Only the PLAYER's choices count here: the coach's already follow from the proofs.
        """
        country = self.held.get("country")
        region = self.held.get("region")
        return (country.country if country and country.by == "user" else None,
                region.region if region and region.by == "user" else None,
                {r.country for r in self.rejected if r.level == "country"},
                {r.region for r in self.rejected if r.level == "region"})

    def country(self) -> str | None:
        """Locked country, by whoever: tips, map and tie-break centre on it."""
        held = self.held.get("country")
        return held.country if held else None

    def as_dict(self) -> dict[str, Any]:
        return {"held": {level: asdict(lock) for level, lock in self.held.items()},
                "rejected": [asdict(r) for r in self.rejected],
                "proposal": asdict(self.proposal) if self.proposal else None}

    # --- internal ------------------------------------------------------------------------------
    def _set(self, lock: Lock) -> None:
        held = self.held.get(lock.level)
        if held and held.same(lock) and held.by == lock.by:
            return
        self.held[lock.level] = lock
        # Order country › region › city, and levels below that are no longer inside it: removed.
        for below in LEVELS[LEVELS.index(lock.level) + 1:]:
            child = self.held.get(below)
            if child and not self._inside(child, lock):
                self.held.pop(below)
        self.held = {level: self.held[level] for level in LEVELS if level in self.held}
        self._drop_orphan_proposal()
        self._event("lock", lock)

    @staticmethod
    def _inside(child: Lock, parent: Lock) -> bool:
        return child.country == parent.country and (parent.level != "region" or child.region == parent.region)

    def _fits(self, lock: Lock) -> bool:
        """Within the locks in place, and outside the rejected countries and regions."""
        _, _, countries, regions = self.scope()
        return (lock.country not in countries and not (lock.region and lock.region in regions)
                and all(self._inside(lock, held) for held in self.held.values() if held.level != lock.level))

    def _drop_orphan_proposal(self) -> None:
        if self.proposal and not self._fits(self.proposal):
            self.proposal = None

    def _rejected(self, lock: Lock) -> bool:
        return any(r.same(lock) for r in self.rejected)

    def _event(self, event: str, lock: Lock) -> None:
        self.events.append({"at": datetime.now().isoformat(timespec="seconds"), "event": event, "by": lock.by,
                            "level": lock.level, "country": lock.country, "region": lock.region, "name": lock.name})


def restrict(found: list[Evidence], scope: Scope) -> list[Evidence]:
    """Restricts a mark's proofs to what the player chose, and removes from them what they rejected.

    Used to locate the view under their choices (namesakes in their country, their region), NEVER to conclude: the
    marks' conclusion stays independent. A proof that no longer points to anything keeps the reason ("outside the
    locked country"). The alphabet is restricted only by rejections: Cyrillic under a "France" lock must stay a visible
    contradiction, not become an alphabet without a country.
    """
    country, region, no_countries, no_regions = scope
    for e in found:
        if e.kind == "lieu" and e.points:
            def keep(p: list[Any]) -> bool:
                where = p[4] if len(p) > 4 else ""
                return not (where and where in no_regions) and not (
                    region and p[2] == region.split(".")[0] and where != region)
            points = [p for p in e.points if keep(p)]
            if not points and not e.note:
                e.note = t("locks.note.outside_region") if region else t("locks.note.rejected_region")
            e.points = points
            e.countries = [c for c in e.countries if any(p[2] == c for p in points)]
        if e.kind == "alphabet":
            e.countries = [c for c in e.countries if c not in no_countries] or e.countries
            continue
        inside = [c for c in e.countries if c not in no_countries and (country is None or c == country)]
        if e.countries and not inside and not e.note:
            e.note = t("locks.note.outside_country" if country else "locks.note.rejected_country",
                       list=", ".join(e.countries[:4]))
        e.countries = inside
        if e.kind == "lieu":  # namesakes of the remaining countries only (keep_nearby re-derives the countries)
            e.points = [p for p in e.points if p[2] in inside]
    return found
