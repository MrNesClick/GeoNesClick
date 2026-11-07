"""Chemins partagés, sans dépendance lourde (importé par le client du raccourci clavier)."""

import os
from pathlib import Path

SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "geonesclick.sock"
