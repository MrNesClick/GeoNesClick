"""Debug mode: JSON log of each analysis, next to its capture (capture-<id>.json).

Written only if [debug] enabled is true (off by default). It is filled in as results arrive
(StreetCLIP, zones, vision model, "Where was it?") and lets you replay a round afterwards to
check or measure it. Local, deleted with old captures (prune_captures). It contains no key
and no account data.
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
        self._lock = threading.Lock()  # results arrive from different tasks
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write()

    def update(self, **fields: Any) -> None:
        with self._lock:
            self.data.update(fields)
            self._write()

    def _write(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1, default=str))
        tmp.replace(self.path)  # never a half-written file
