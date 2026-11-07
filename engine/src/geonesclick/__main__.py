import os
from pathlib import Path

from .apikey import key_file, migrate_env
from .config import PROJECT_ROOT, load_config
from .paths import migrate_legacy


def _hf_model_cached(model_id: str) -> bool:
    """Le modèle est-il déjà dans le cache Hugging Face local ? (sans importer la bibliothèque)"""
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub_cache = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub"))
    snapshots = hub_cache / f"models--{model_id.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


# Le niveau 1 doit fonctionner hors ligne et ne rien envoyer sur le réseau : une fois les modèles locaux en
# cache (StreetCLIP, et PLONK s'il est activé), on active le mode hors ligne AVANT d'importer transformers
# (il lit la variable à l'import). Tant qu'un modèle manque, il reste possible de le télécharger.
for _moved in migrate_legacy():  # ancien nom (GeoNesClick) : dossiers déplacés une fois, jamais supprimés
    print(f"GeoNesClick : {_moved}", flush=True)
_cfg = load_config()
if migrate_env(_cfg.vision.api_key_env, PROJECT_ROOT / ".env"):  # clé de l'ancien .env : vers le fichier protégé
    print(f"GeoNesClick : clé {_cfg.vision.api_key_env} déplacée du .env vers {key_file(_cfg.vision.api_key_env)}",
          flush=True)
_models = [_cfg.streetclip.model] + ([_cfg.plonk.model] if _cfg.plonk.enabled else [])
if all(_hf_model_cached(m) for m in _models):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from .server import main  # noqa: E402

main()
