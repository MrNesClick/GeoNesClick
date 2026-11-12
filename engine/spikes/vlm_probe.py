"""Trial of an NVIDIA vision model: image → structured clue sheet (JSON).

Usage: .venv/bin/python spikes/vlm_probe.py [--model ID] [--crop L,T,R,B] image.png

The model only DESCRIBES what it sees (the "vision" role in the architecture): no country is
asked for here. The key is read from the .env file at the project root (variable NVAPI).
"""

from __future__ import annotations

import argparse
import base64
import io
import tomllib
import json
import time
from pathlib import Path

from openai import OpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "z-ai/glm-5.3-flash"
MAX_SIDE = 1280  # px: trade-off between readable details and request size

def prompt() -> str:
    """The app's vision prompt (default_config.toml), answers in English."""
    cfg = tomllib.loads((ROOT / "engine/src/geonesclick/default_config.toml").read_text())
    return cfg["vision"]["prompt"].replace("{language}", "English")


def load_key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("NVAPI="):
            key = line.split("=", 1)[1].strip().strip("\"'")
            if key:
                return key
    raise SystemExit("NVAPI missing or empty in .env")


def encode(path: Path, crop: tuple[int, int, int, int] | None) -> str:
    img = Image.open(path).convert("RGB")
    if crop:
        img = img.crop(crop)
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("image", type=Path)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--crop", help="left,top,right,bottom in pixels")
    args = p.parse_args()
    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else None

    client = OpenAI(base_url=BASE_URL, api_key=load_key(), timeout=90, max_retries=0)
    b64 = encode(args.image, crop)
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=args.model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt()},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        temperature=0.2,
        max_tokens=4000,  # reasoning models consume tokens before answering
    )
    elapsed = time.perf_counter() - t0
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.total_tokens if resp.usage else "?"
    print(f"Model: {args.model}  |  latency: {elapsed:.1f} s  |  tokens: {tokens}\n")
    start, end = text.find("{"), text.rfind("}")
    try:
        print(json.dumps(json.loads(text[start:end + 1]), ensure_ascii=False, indent=2))
    except ValueError:
        print("[non-JSON answer]\n" + text)


if __name__ == "__main__":
    main()
