"""Writes the engine answers replayed by the interface tests (app/e2e/fixtures/), produced by the REAL engine.

    cd engine && .venv/bin/python ../app/e2e/make_fixtures.py

The engine runs in memory (no server, no network) in temporary folders, never your own settings, with a simulated
capture and StreetCLIP (a Swedish view: Sweden 57 %, Finland 35 %, Norway 6 %), like the engine's own tests. Run it
again after a change of the engine's answers: tests/test_e2e_fixtures.py fails while the fixtures are out of date.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixtures"


def produce(out: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gnc-fixtures-"))
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "HF_HOME"):
        os.environ[var] = str(tmp / var.lower())
    # Imported only now: the engine's folders are computed at import, from the variables above.
    from fastapi.testclient import TestClient
    from PIL import Image

    from geonesclick import capture, server
    from geonesclick.config import load_config
    from geonesclick.streetclip import CountryScore

    user = tmp / "config.toml"
    user.write_text('[capture]\nnotify = false\nsave_to_disk = false\n\n[coach]\nlanguage = "en"\n')
    app = server.create_app(load_config(user), settings_path=user)
    engine = app.state.engine
    client = TestClient(app, base_url="http://127.0.0.1:47615")
    origin = {"Origin": "http://localhost:1420"}

    class FakeClip:
        device = "cpu"

        def analyse(self, _img):
            scores = [CountryScore("Sweden", "SE", 0.57), CountryScore("Finland", "FI", 0.35),
                      CountryScore("Norway", "NO", 0.06), CountryScore("Estonia", "EE", 0.01),
                      CountryScore("Denmark", "DK", 0.004)]
            return scores, 1600.0, None, None

    engine.capture.grab = lambda: Image.new("RGB", (64, 40), (90, 140, 200))
    engine.streetclip = FakeClip()
    engine.vision.client = None
    ids = iter(f"cap{n}" for n in range(1, 100))
    capture.new_id = server.new_id = lambda: next(ids)  # stable ids: the fixtures do not change from run to run
    sent: list[dict] = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast

    async def round_():
        await engine.analyse()
        await asyncio.gather(*engine.background)

    asyncio.run(round_())
    import tomllib

    from geonesclick import paths
    files = {
        # The installer's list of downloads, as scripts/bundle_meta.py writes it into the AppImage.
        "downloads.json": tomllib.loads((Path(paths.__file__).parent / "downloads.toml").read_text()),
        "state.json": engine.state(),
        # Time and duration of the capture change from run to run: fixed, like the ids.
        "round-sweden.json": [{**m, "at": "2026-11-12T15:00:00", "ms": 330} if m["type"] == "capture" else m
                              for m in sent if m["type"] in ("capture", "streetclip")],
    }
    for path in ("/settings", "/settings/file-only", "/storage", "/storage/erase", "/progress"):
        res = client.get(path, headers=origin)
        files[path.strip("/").replace("/", "-") + ".json"] = res.json()
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        (out / name).write_text(text.replace(str(tmp), "/home/player") + "\n", encoding="utf-8")


if __name__ == "__main__":
    produce(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
    print(f"fixtures written to {OUT if len(sys.argv) == 1 else sys.argv[1]}")
