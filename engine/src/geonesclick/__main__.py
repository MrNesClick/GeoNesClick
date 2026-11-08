import os

from .apikey import key_file, migrate_env
from .config import PROJECT_ROOT, load_config
from .paths import hf_hub_cache, migrate_repo_data


def _hf_model_cached(model_id: str, revision: str) -> bool:
    """Is the pinned version of the model already cached, weights included? (without importing the library)"""
    snapshot = hf_hub_cache() / f"models--{model_id.replace('/', '--')}" / "snapshots" / revision
    return all((snapshot / name).is_file() for name in ("config.json", "model.safetensors"))


# Level 1 must work offline and send nothing over the network: once the local models are
# cached (StreetCLIP, and PLONK if enabled), offline mode is turned on BEFORE importing transformers
# (it reads the variable at import). As long as a model is missing, it can still be downloaded.
# Captures and the test set move out of the code folder once (read-only in an AppImage).
for _moved in migrate_repo_data(PROJECT_ROOT):
    print(f"GeoNesClick: {_moved}", flush=True)
_cfg = load_config()
if migrate_env(_cfg.vision.api_key_env, PROJECT_ROOT / ".env"):  # key from the old .env: moved to the protected file
    print(f"GeoNesClick: key {_cfg.vision.api_key_env} moved from the .env to {key_file(_cfg.vision.api_key_env)}",
          flush=True)
_models = [(_cfg.streetclip.model, _cfg.streetclip.revision)] + (
    [(_cfg.plonk.model, _cfg.plonk.revision)] if _cfg.plonk.enabled else [])
if all(_hf_model_cached(m, r) for m, r in _models):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from .server import main  # noqa: E402

main()
