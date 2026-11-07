import os

from .apikey import key_file, migrate_env
from .config import PROJECT_ROOT, load_config
from .paths import hf_hub_cache, migrate_legacy, migrate_repo_data


def _hf_model_cached(model_id: str, revision: str) -> bool:
    """La version figée du modèle est-elle déjà en cache, poids compris ? (sans importer la bibliothèque)"""
    snapshot = hf_hub_cache() / f"models--{model_id.replace('/', '--')}" / "snapshots" / revision
    return all((snapshot / name).is_file() for name in ("config.json", "model.safetensors"))


# Le niveau 1 doit fonctionner hors ligne et ne rien envoyer sur le réseau : une fois les modèles locaux en
# cache (StreetCLIP, et PLONK s'il est activé), on active le mode hors ligne AVANT d'importer transformers
# (il lit la variable à l'import). Tant qu'un modèle manque, il reste possible de le télécharger.
# Ancien nom (GeoNesClick) : dossiers déplacés une fois, jamais supprimés ; puis captures et jeu de test sortent
# du dossier du code (lecture seule dans une AppImage).
for _moved in migrate_legacy() + migrate_repo_data(PROJECT_ROOT):
    print(f"GeoNesClick : {_moved}", flush=True)
_cfg = load_config()
if migrate_env(_cfg.vision.api_key_env, PROJECT_ROOT / ".env"):  # clé de l'ancien .env : vers le fichier protégé
    print(f"GeoNesClick : clé {_cfg.vision.api_key_env} déplacée du .env vers {key_file(_cfg.vision.api_key_env)}",
          flush=True)
_models = [(_cfg.streetclip.model, _cfg.streetclip.revision)] + (
    [(_cfg.plonk.model, _cfg.plonk.revision)] if _cfg.plonk.enabled else [])
if all(_hf_model_cached(m, r) for m, r in _models):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from .server import main  # noqa: E402

main()
