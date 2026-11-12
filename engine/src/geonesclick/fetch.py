"""Download of the models, pinned versions, during installation (first-launch assistant).

    python -m geonesclick.fetch streetclip     # required (1.7 GB)
    python -m geonesclick.fetch plonk          # "likely zones on the map" option (144 MB)

Only the necessary files of the pinned version are downloaded (StreetCLIP: weights in safetensors, never the
pickled pytorch_model.bin). Listed in downloads.toml; the assistant tracks the progress from the cache size.
"""

from __future__ import annotations

import sys

from .config import load_config
from .paths import quiet_token_nag

FILES = {
    "streetclip": ("config.json", "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json",
                   "special_tokens_map.json", "vocab.json", "merges.txt", "model.safetensors"),
    "plonk": ("config.json", "model.safetensors"),
}


def fetch(which: str) -> None:
    import httpx2  # huggingface_hub's HTTP client (httpx is only a test dependency here)
    from huggingface_hub import hf_hub_download

    quiet_token_nag()
    cfg = load_config()
    model, revision = {"streetclip": (cfg.streetclip.model, cfg.streetclip.revision),
                       "plonk": (cfg.plonk.model, cfg.plonk.revision)}[which]
    for name in FILES[which]:
        try:
            hf_hub_download(model, name, revision=revision)
        except (OSError, httpx2.HTTPError) as e:  # Hub unreachable or failing, interrupted transfer, disk full
            raise FetchError(f"{model}/{name}", e) from e
        print(f"FICHIER {model}/{name}", flush=True)


class FetchError(Exception):
    """A model file that could not be downloaded (Hub unreachable, disk full...)."""

    def __init__(self, file: str, cause: Exception):
        from huggingface_hub import constants

        reason = " ".join(f"{type(cause).__name__}: {cause}".split())  # one line, whatever the library wrote
        # Log line, in English like uv's around it; the assistant names the site from it (setup.rs, diagnose).
        super().__init__(f"error: {file} not downloaded from {constants.ENDPOINT}/: {reason}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in FILES:
        print(f"usage : python -m geonesclick.fetch {{{'|'.join(FILES)}}}", file=sys.stderr)
        return 2
    try:
        fetch(argv[0])
    except FetchError as e:
        print(e, file=sys.stderr)  # one readable line instead of a traceback
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
