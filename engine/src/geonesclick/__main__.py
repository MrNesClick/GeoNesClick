import os
from pathlib import Path

from .config import load_config


def _hf_model_cached(model_id: str) -> bool:
    """Le modèle est-il déjà dans le cache Hugging Face local ? (sans importer la bibliothèque)"""
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub_cache = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub"))
    snapshots = hub_cache / f"models--{model_id.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


# Le niveau 1 doit fonctionner hors ligne et ne rien envoyer sur le réseau : une fois le modèle en cache,
# on active le mode hors ligne AVANT d'importer transformers (il lit la variable à l'import).
if _hf_model_cached(load_config().streetclip.model):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from .server import main  # noqa: E402

main()
