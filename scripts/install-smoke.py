"""Run with the installed engine's Python, in a fresh system: does the engine work with this system's libraries?

    ~/.local/share/geonesclick/engine/venv/bin/python install-smoke.py

Checks what the capture needs from the system (GObject Introspection, GStreamer and its PipeWire source, Cairo),
runs a StreetCLIP analysis, imports every module of the engine (a dependency missing from the bundle shows here, not
on the user's machine) and answers a few requests of the interface. Called by scripts/test-install.py in each
distribution's container.
"""
import sys

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # noqa: E402  # needs libgirepository-2.0 and the Gst typelib of the system

Gst.init(None)
missing = [name for name in ("appsink", "videoconvert", "pipewiresrc") if not Gst.ElementFactory.find(name)]
if missing:
    sys.exit(f"GStreamer elements missing: {', '.join(missing)}")

import cairo  # noqa: E402,F401  # pycairo, against the system's libcairo
from PIL import Image  # noqa: E402

from geonesclick.config import load_config  # noqa: E402
from geonesclick.streetclip import StreetClip  # noqa: E402

cfg = load_config().streetclip
scores, ms, *_ = StreetClip(cfg).analyse(Image.new("RGB", (640, 400), (120, 160, 90)))
total = sum(s.probability for s in scores)
if len(scores) != cfg.top_k or not 0 < total <= 1.0001:
    sys.exit(f"unexpected StreetCLIP answer: {scores}")
import importlib  # noqa: E402
import pkgutil  # noqa: E402

import geonesclick  # noqa: E402

# __main__ starts the engine when imported; its own imports are other modules of the package.
modules = [m.name for m in pkgutil.walk_packages(geonesclick.__path__, "geonesclick.") if not m.name.endswith("__main__")]
failed = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001  # every module is tried, all failures are reported together
        failed.append(f"{name}: {type(exc).__name__}: {exc}")
if failed:
    sys.exit("engine modules that do not import:\n" + "\n".join(failed))

from fastapi.testclient import TestClient  # noqa: E402

from geonesclick.server import create_app  # noqa: E402

# Without the startup (no "with"): no capture, download or network, only the answers the interface asks for first.
client = TestClient(create_app(load_config()), base_url="http://127.0.0.1:47615")
for route in ("/health", "/settings", "/storage"):
    res = client.get(route, headers={"Origin": "http://tauri.localhost"})
    if res.status_code != 200 or not res.json():
        sys.exit(f"the engine does not answer {route}: {res.status_code} {res.text[:200]}")
print(f"engine OK: GStreamer {Gst.version_string()}, StreetCLIP in {ms:.0f} ms, top {scores[0].code}, "
      f"{len(modules)} modules, interface requests answered")
