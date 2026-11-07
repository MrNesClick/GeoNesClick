"""Verrous pays › région › ville : ce qui est fixé pour la capture en cours, et qui l'a fixé.

Décidé avec l'utilisateur le 2026-11-07 (démarche OSINT : fixer ce qui est sûr, puis resserrer) :
- le COACH verrouille seul le pays « certain » et la région d'un point net ; une ville, il la PROPOSE seulement
  (un panneau « Pau 40 km » nomme un lieu où l'on n'est pas) ; ses verrous suivent les preuves (une marque retirée
  peut les défaire) ;
- l'HUMAIN peut toujours rejeter un verrou (✕) : le rejet dure toute la capture, le coach ne re-verrouille pas la
  même chose ; il peut aussi verrouiller lui-même, et le coach ne remplace jamais ce verrou ;
- un verrou humain à un niveau entraîne les niveaux du dessus (« Orthez » : la France, la Nouvelle-Aquitaine) ; un
  rejet emporte les niveaux du dessous, qui en dépendaient ;
- tout est journalisé (mode débogage) pour mesurer les erreurs des règles ;
- les verrous durent une capture : une nouvelle capture repart de zéro (un verrou périmé fausserait la suivante).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any

from .evidence import Evidence
from .places import normalise

LEVELS = ("country", "region", "city")
Scope = tuple[str | None, str | None, set[str], set[str]]  # voir Locks.scope
NO_SCOPE: Scope = (None, None, set(), set())


@dataclass
class Lock:
    level: str  # "country", "region" ou "city"
    country: str  # code ISO à 2 lettres
    region: str = ""  # code GeoNames de la région (« FR.75 ») : région, et ville si on la connaît
    name: str = ""  # région ou ville telle qu'affichée (le pays : l'interface a son nom)
    lat: float | None = None  # ville
    lon: float | None = None
    by: str = "coach"  # "coach" ou "user"
    why: str = ""  # ce qui l'a fait poser (coach : les marques qui le prouvent)

    def same(self, other: Lock) -> bool:
        """Même lieu au même niveau, quel que soit l'auteur."""
        if self.level != other.level or self.country != other.country:
            return False
        if self.level == "country":
            return True
        if self.level == "region":
            return self.region == other.region
        return normalise(self.name) == normalise(other.name) and self.region == other.region


@dataclass
class Locks:
    held: dict[str, Lock] = field(default_factory=dict)  # niveau → verrou, dans l'ordre pays, région, ville
    rejected: list[Lock] = field(default_factory=list)
    proposal: Lock | None = None  # ville proposée par le coach (un clic pour la verrouiller)
    events: list[dict[str, Any]] = field(default_factory=list)

    # --- humain --------------------------------------------------------------------------------
    def lock(self, lock: Lock, region_name: str = "") -> None:
        """Verrou posé par le joueur (ou proposition acceptée), avec les niveaux du dessus.

        region_name : nom de la région d'une ville (sinon celui du verrou en place, ou son code).
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
            self.rejected = [r for r in self.rejected if not r.same(item)]  # le joueur l'emporte sur son rejet
            self._set(item)
        if self.proposal and lock.level == "city":
            self.proposal = None

    def reject(self, level: str) -> Lock:
        """✕ sur un verrou (ou sur la proposition, level « proposal ») : écarté pour toute la capture."""
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
        """Ce que les preuves permettent maintenant ; les verrous du joueur et ses rejets l'emportent."""
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

    # --- ce qui restreint la recherche ---------------------------------------------------------
    def scope(self) -> tuple[str | None, str | None, set[str], set[str]]:
        """(pays verrouillé, région verrouillée, pays rejetés, régions rejetées) pour les règles des marques.

        Seuls les verrous du JOUEUR restreignent les preuves : ceux du coach en découlent déjà, et s'en servir
        pour filtrer les preuves les rendrait impossibles à défaire par une nouvelle marque.
        """
        country = self.held.get("country")
        region = self.held.get("region")
        return (country.country if country and country.by == "user" else None,
                region.region if region and region.by == "user" else None,
                {r.country for r in self.rejected if r.level == "country"},
                {r.region for r in self.rejected if r.level == "region"})

    def country(self) -> str | None:
        """Pays verrouillé, par qui que ce soit : astuces, carte et départage s'y centrent."""
        held = self.held.get("country")
        return held.country if held else None

    def as_dict(self) -> dict[str, Any]:
        return {"held": {level: asdict(lock) for level, lock in self.held.items()},
                "rejected": [asdict(r) for r in self.rejected],
                "proposal": asdict(self.proposal) if self.proposal else None}

    # --- interne -------------------------------------------------------------------------------
    def _set(self, lock: Lock) -> None:
        held = self.held.get(lock.level)
        if held and held.same(lock) and held.by == lock.by:
            return
        self.held[lock.level] = lock
        # Ordre pays › région › ville, et niveaux du dessous qui ne sont plus dedans : retirés.
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
        """Dans les verrous en place, et hors des pays et régions rejetés."""
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
    """Restreint les preuves d'une marque à ce que le joueur a verrouillé, et en retire ce qu'il a rejeté.

    Une preuve qui ne désigne plus rien reste affichée avec la raison (« hors du pays verrouillé ») : c'est une
    preuve contraire, visible, jamais effacée. L'alphabet n'est restreint que par les rejets : du cyrillique sous un
    verrou « France » doit rester une contradiction visible, pas devenir un alphabet sans pays.
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
                e.note = "hors de la région verrouillée" if region else "dans une région rejetée"
            e.points = points
            e.countries = [c for c in e.countries if any(p[2] == c for p in points)]
        if e.kind == "alphabet":
            e.countries = [c for c in e.countries if c not in no_countries] or e.countries
            continue
        inside = [c for c in e.countries if c not in no_countries and (country is None or c == country)]
        if e.countries and not inside and not e.note:
            e.note = (f"hors du pays verrouillé ({', '.join(e.countries[:4])})" if country
                      else f"pays rejeté ({', '.join(e.countries[:4])})")
        e.countries = inside
        if e.kind == "lieu":  # homonymes : seulement ceux des pays restants (keep_nearby en redéduit les pays)
            e.points = [p for p in e.points if p[2] in inside]
    return found
