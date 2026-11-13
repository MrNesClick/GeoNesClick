"""Screen capture through the ScreenCast portal (xdg-desktop-portal) + PipeWire + GStreamer.

Everything touching GLib (D-Bus, GStreamer) lives in a dedicated thread that runs the GLib loop.
The first opening shows the GNOME picker; the restore token (persist_mode=2) avoids
asking again afterwards.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import secrets
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gio, GLib, Gst  # noqa: E402
from PIL import Image, ImageStat  # noqa: E402

from .i18n import t
from .config import CONFIG_DIR  # noqa: E402

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SOURCE_MONITOR, SOURCE_WINDOW = 1, 2
CURSOR_HIDDEN = 1
PERSIST_UNTIL_REVOKED = 2
TOKEN_FILE = CONFIG_DIR / "screencast.token"


class CaptureError(RuntimeError):
    pass


class _Portal:
    """Minimal driver for the ScreenCast portal (asynchronous requests with a Response signal)."""

    def __init__(self, loop: GLib.MainLoop) -> None:
        self.loop = loop
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.sender = self.bus.get_unique_name()[1:].replace(".", "_")
        self.session_handle: str | None = None

    def _request(self, method: str, signature: str, args: tuple, options: dict[str, GLib.Variant]) -> dict:
        token = f"gnc_{secrets.token_hex(6)}"
        request_path = f"{PORTAL_PATH}/request/{self.sender}/{token}"
        result: dict = {}

        def on_response(_conn, _sender, _path, _iface, _signal, data):
            result["code"], result["results"] = data.unpack()
            self.loop.quit()

        sub = self.bus.signal_subscribe(
            PORTAL_BUS, REQUEST_IFACE, "Response", request_path, None,
            Gio.DBusSignalFlags.NO_MATCH_RULE, on_response,
        )
        params = GLib.Variant(signature, (*args, {**options, "handle_token": GLib.Variant("s", token)}))
        try:
            self.bus.call_sync(
                PORTAL_BUS, PORTAL_PATH, SCREENCAST_IFACE, method, params,
                GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None,
            )
            self.loop.run()
        finally:
            self.bus.signal_unsubscribe(sub)
        if result.get("code") != 0:
            raise CaptureError(t("capture.refused", method=method, code=result.get("code")))
        return result["results"]

    def open(self, source_types: int) -> tuple[int, int]:
        res = self._request("CreateSession", "(a{sv})", (), {
            "session_handle_token": GLib.Variant("s", f"gnc_{secrets.token_hex(4)}"),
        })
        self.session_handle = res["session_handle"]
        options = {
            "types": GLib.Variant("u", source_types),
            "multiple": GLib.Variant("b", False),
            "cursor_mode": GLib.Variant("u", CURSOR_HIDDEN),
            "persist_mode": GLib.Variant("u", PERSIST_UNTIL_REVOKED),
        }
        if TOKEN_FILE.exists():
            options["restore_token"] = GLib.Variant("s", TOKEN_FILE.read_text().strip())
        self._request("SelectSources", "(oa{sv})", (self.session_handle,), options)
        res = self._request("Start", "(osa{sv})", (self.session_handle, ""), {})
        if token := res.get("restore_token"):
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            # Created directly as 0600: no moment when the token would be readable by others.
            fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(token)
        node_id = res["streams"][0][0]
        reply, fd_list = self.bus.call_with_unix_fd_list_sync(
            PORTAL_BUS, PORTAL_PATH, SCREENCAST_IFACE, "OpenPipeWireRemote",
            GLib.Variant("(oa{sv})", (self.session_handle, {})),
            GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None,
        )
        return fd_list.get(reply.unpack()[0]), node_id

    def close(self) -> None:
        if self.session_handle:
            try:
                self.bus.call_sync(
                    PORTAL_BUS, self.session_handle, "org.freedesktop.portal.Session", "Close",
                    None, None, Gio.DBusCallFlags.NONE, 2000, None,
                )
            except GLib.Error:
                pass  # session already closed (sharing stopped by the user)


class CaptureService:
    """Continuous stream of the shared window; `grab()` returns the last image received."""

    SOURCES = {"window": SOURCE_WINDOW, "monitor": SOURCE_MONITOR, "both": SOURCE_WINDOW | SOURCE_MONITOR}

    def __init__(self, on_state: Callable[[bool, str, bool, bool], None], source: str = "window") -> None:
        # Called from the capture threads: (stream active?, message, cut off midway?, picker about to open?)
        self._on_state = on_state
        self._source_types = self.SOURCES[source]
        self._lock = threading.Lock()
        self._latest: Gst.Sample | None = None
        self._alive = False
        self._thread: threading.Thread | None = None
        self._loop: GLib.MainLoop | None = None
        self._pipeline: Gst.Pipeline | None = None
        self._portal: _Portal | None = None
        self._stopping = False
        self._got_frame = False  # the current stream has delivered an image
        self._error: str | None = None  # why the current stream died
        Gst.init(None)

    @property
    def alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopping = False
        self._thread = threading.Thread(target=self._run, name="glib-capture", daemon=True)
        self._thread.start()

    def restart(self, forget_window: bool = False) -> None:
        """Restarts the sharing; with forget_window, forgets the remembered window and reopens the GNOME picker."""
        self.stop()
        if forget_window:
            TOKEN_FILE.unlink(missing_ok=True)
        self.start()

    def stop(self) -> None:
        self._stopping = True
        if loop := self._loop:
            # The request must go through the capture thread's GLib context: GLib.idle_add()
            # would target the default context, which nobody runs. The loop is held here: self._loop is cleared below
            # even when the thread outlives the join.
            source = GLib.idle_source_new()
            source.set_callback(lambda *_: loop.quit())
            source.attach(loop.get_context())
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = self._pipeline = self._portal = None

    def _run(self) -> None:
        ctx = GLib.MainContext.new()
        ctx.push_thread_default()
        try:
            self._loop = GLib.MainLoop.new(ctx, False)
            message, interrupted = self._share()
        finally:
            ctx.pop_thread_default()
        if message or self._alive:
            self._set_alive(False, message or t("capture.stopped"), interrupted)

    def _share(self) -> tuple[str | None, bool]:
        """Shares the remembered window, or the one picked in GNOME. A remembered window that no longer exists is
        accepted by GNOME, then its stream dies before its first image ("target not found"): it is forgotten and the
        picker opens, once. Returns how the sharing ended: (error message or None if stopped, cut off midway?)."""
        resumed = TOKEN_FILE.exists()
        ended = self._stream()
        if resumed and ended[0] and not self._got_frame:  # a sharing stopped by the app ends without error
            TOKEN_FILE.unlink(missing_ok=True)
            self._on_state(False, t("capture.window_gone"), False, True)
            ended = self._stream()
        return ended

    def _stream(self) -> tuple[str | None, bool]:
        """One sharing, from the portal to the end of its stream (see _share for the result)."""
        self._got_frame, self._error, self._portal = False, None, None
        try:
            self._portal = _Portal(self._loop)
            fd, node_id = self._portal.open(self._source_types)
            self._pipeline = Gst.parse_launch(
                f"pipewiresrc fd={fd} path={node_id} always-copy=true do-timestamp=true "
                "! videoconvert ! video/x-raw,format=RGBA "
                "! appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false"
            )
            self._pipeline.get_by_name("sink").connect("new-sample", self._on_sample)
            bus = self._pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message::error", self._on_error)
            self._pipeline.set_state(Gst.State.PLAYING)
            self._loop.run()
        except Exception as exc:  # portal refused, PipeWire missing… (or the picker closed by stop())
            return (None, False) if self._stopping else (t("capture.unavailable", error=exc), False)
        finally:
            if self._pipeline:
                self._pipeline.set_state(Gst.State.NULL)  # no image arrives once this returns
                self._pipeline.get_bus().remove_signal_watch()  # a second stream runs in the same GLib context
                self._pipeline = None
            if self._portal:
                self._portal.close()
        return (None, False) if self._stopping or self._error is None else (self._error, True)

    def _set_alive(self, alive: bool, message: str, interrupted: bool = False) -> None:
        with self._lock:
            self._alive = alive
            if not alive:
                self._latest = None  # never return a stale image
        self._on_state(alive, message, interrupted, False)

    def _on_sample(self, sink) -> Gst.FlowReturn:
        """Called from GStreamer's streaming thread. The sharing is announced active with its first image only: a
        stream that the portal accepted can still die before showing anything."""
        sample = sink.emit("pull-sample")
        with self._lock:
            self._latest = sample
            first = not self._got_frame
            self._got_frame = True
        if first:
            self._set_alive(True, t("capture.active"))
        return Gst.FlowReturn.OK

    def _on_error(self, _bus, msg) -> None:
        err, _dbg = msg.parse_error()
        self._error = t("capture.interrupted", error=err.message)
        self._loop.quit()

    def grab(self) -> Image.Image:
        with self._lock:
            sample, alive = self._latest, self._alive
        if not alive and not (self._thread and self._thread.is_alive()):
            raise CaptureError(t("capture.inactive"))
        if sample is None:
            raise CaptureError(t("capture.no_image"))
        caps = sample.get_caps().get_structure(0)
        width, height = caps.get_value("width"), caps.get_value("height")
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if not ok:
            raise CaptureError(t("capture.buffer"))
        try:
            stride = len(info.data) // height
            img = Image.frombuffer("RGBA", (width, height), bytes(info.data), "raw", "RGBA", stride, 1)
        finally:
            buf.unmap(info)
        return img.convert("RGB")


PADDING_LEVEL = 2  # a padding pixel is pure black; video compression leaves at most this on each channel
_NOT_PADDING = ([0] * (PADDING_LEVEL + 1) + [255] * (255 - PADDING_LEVEL)) * 3  # per channel: padding → 0


def trim_padding(img: Image.Image) -> Image.Image:
    """The shared window without the black padding around it: GNOME keeps the stream at the size it started with, so a
    window shrunk during the sharing is drawn at the top left with the rest pure black, and the window's shadow comes
    out black too (a maximised window leaves 32 black rows at the bottom). Whole black columns and rows go on every
    side; a frame black all over is left as it is. About 10 ms on a 4K frame."""
    box = (img if img.mode == "RGB" else img.convert("RGB")).point(_NOT_PADDING).getbbox()
    return img if box is None or box == (0, 0, *img.size) else img.crop(box)


# Grey-level spread under which a view is plain (black, white, a loading screen): the least contrasted view of the
# test set, a snowfield under a white sky, has 22.5; a single colour has 0.
FLAT_SPREAD = 6


def is_flat(img: Image.Image) -> bool:
    small = img.convert("L")
    small.thumbnail((64, 64))
    return ImageStat.Stat(small).stddev[0] < FLAT_SPREAD


def fingerprint(img: Image.Image) -> bytes:
    """Same pixels, same fingerprint: tells a capture identical to the previous one (a frozen sharing)."""
    return hashlib.blake2b(img.tobytes(), digest_size=16).digest()


THUMB_SIDE = 720  # thumbnail of a capture sent to the UI


def data_url(img: Image.Image, side: int = THUMB_SIDE, quality: int = 82) -> str:
    img = img.copy()
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def new_id() -> str:
    """Timestamped identifier of a capture or a frozen view (also used as the file name)."""
    return f"{datetime.now():%Y%m%d-%H%M%S}-{time.time_ns() % 1000:03d}"



def apply_crop_and_masks(img: Image.Image, crop: list[float], masks: list[list[float]]) -> Image.Image:
    """Crops (fractions [l, t, r, b]) then blacks out the masked zones (fractions of the cropped zone)."""
    if len(crop) == 4:
        w, h = img.size
        img = img.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    if masks:
        img = img.copy()
        w, h = img.size
        for m in masks:
            if len(m) == 4:
                img.paste((0, 0, 0), (int(m[0] * w), int(m[1] * h), int(m[2] * w), int(m[3] * h)))
    return img


def save_png(img: Image.Image, directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.png"
    img.save(path)
    return path


def prune_captures(directory: Path, keep: int) -> int:
    """Keeps only the `keep` most recent captures (timestamped names). Returns the number deleted."""
    files = sorted(directory.glob("capture-*.png"))
    old = files[:-keep] if keep else []
    for f in old:
        f.unlink(missing_ok=True)
        f.with_suffix(".json").unlink(missing_ok=True)  # debug mode log
        _unlink_marks(directory, f.stem)
    logs = sorted(directory.glob("capture-*.json"))  # logs without an image (capture copies turned off)
    for f in logs[:-keep] if keep else []:
        f.unlink(missing_ok=True)
        _unlink_marks(directory, f.stem)
    return len(old)


def _unlink_marks(directory: Path, capture_stem: str) -> None:
    """Mark crops (debug mode) of a deleted capture: mark-<id>-<n>.png."""
    for f in directory.glob(f"mark-{capture_stem.removeprefix('capture-')}-*.png"):
        f.unlink(missing_ok=True)
