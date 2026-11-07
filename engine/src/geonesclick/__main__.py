import os
from pathlib import Path

from .config import load_config


def _hf_model_cached(model_id: str) -> bool:
    """Le modèle est-il déjà dans le cache Hugging Face local ? (sans importer la bibliothèque)"""
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub_cache = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub"))
    snapshots = hub_cache / f"models--{model_id.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


# Le niveau 1 doit fonctionner hors ligne et ne rien envoyer sur le réseau : une fois les modèles locaux en
# cache (StreetCLIP, et PLONK s'il est activé), on active le mode hors ligne AVANT d'importer transformers
# (il lit la variable à l'import). Tant qu'un modèle manque, il reste possible de le télécharger.
_cfg = load_config()
_models = [_cfg.streetclip.model] + ([_cfg.plonk.model] if _cfg.plonk.enabled else [])
if all(_hf_model_cached(m) for m in _models):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from .server import main  # noqa: E402

main()
