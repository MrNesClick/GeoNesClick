"""Run with the installed engine's Python, in a fresh system: does the engine work with this system's libraries?

    ~/.local/share/geonesclick/engine/venv/bin/python install-smoke.py

Checks what the capture needs from the system (GObject Introspection, GStreamer and its PipeWire source, Cairo),
then runs a StreetCLIP analysis. Called by scripts/test-install.py in each distribution's container.
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
print(f"engine OK: GStreamer {Gst.version_string()}, StreetCLIP in {ms:.0f} ms, top {scores[0].code}")
