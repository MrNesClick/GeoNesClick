"""Download of the models, pinned versions, during installation (first-launch assistant).

    python -m geonesclick.fetch streetclip     # required (1.7 GB)
    python -m geonesclick.fetch plonk          # "likely zones on the map" option (144 MB)

Only the necessary files of the pinned version are downloaded (StreetCLIP: weights in safetensors, never the
pickled pytorch_model.bin). Listed in downloads.toml; the assistant tracks the progress from the cache size.
"""

from __future__ import annotations

import sys

from .config import load_config

FILES = {
    "streetclip": ("config.json", "preprocessor_config.json", "tokenizer.json", "tokenizer_config.json",
                   "special_tokens_map.json", "vocab.json", "merges.txt", "model.safetensors"),
    "plonk": ("config.json", "model.safetensors"),
}


def fetch(which: str) -> None:
    from huggingface_hub import hf_hub_download

    cfg = load_config()
    model, revision = {"streetclip": (cfg.streetclip.model, cfg.streetclip.revision),
                       "plonk": (cfg.plonk.model, cfg.plonk.revision)}[which]
    for name in FILES[which]:
        hf_hub_download(model, name, revision=revision)
        print(f"FICHIER {model}/{name}", flush=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in FILES:
        print(f"usage : python -m geonesclick.fetch {{{'|'.join(FILES)}}}", file=sys.stderr)
        return 2
    fetch(argv[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
