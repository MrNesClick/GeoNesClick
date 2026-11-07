"""Mode débogage : journal JSON de chaque analyse, à côté de sa capture (capture-<id>.json).

Écrit seulement si [debug] enabled est vrai (coupé par défaut). Il se complète au fil des résultats
(StreetCLIP, zones, modèle de vision, « C'était où ? ») et permet de relire une manche après coup pour la
vérifier ou la mesurer. Local, supprimé avec les anciennes captures (prune_captures). Il ne contient ni clé
ni donnée de compte.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


class AnalysisLog:
    def __init__(self, path: Path, base: dict[str, Any]) -> None:
        self.path = path
        self.data = dict(base)
        self._lock = threading.Lock()  # les résultats arrivent de tâches différentes
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write()

    def update(self, **fields: Any) -> None:
        with self._lock:
            self.data.update(fields)
            self._write()

    def _write(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1, default=str))
        tmp.replace(self.path)  # jamais de fichier à moitié écrit
