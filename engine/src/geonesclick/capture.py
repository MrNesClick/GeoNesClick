"""Capture d'écran via le portail ScreenCast (xdg-desktop-portal) + PipeWire + GStreamer.

Tout ce qui touche à GLib (D-Bus, GStreamer) vit dans un thread dédié qui fait tourner la boucle GLib.
La première ouverture affiche le sélecteur de GNOME ; le jeton de restauration (persist_mode=2) évite
de redemander ensuite.
"""

from __future__ import annotations

import os
import secrets
import threading
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gio, GLib, Gst  # noqa: E402
from PIL import Image  # noqa: E402

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
    """Pilote minimal du portail ScreenCast (requêtes asynchrones avec signal Response)."""

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
            raise CaptureError(f"partage refusé ou annulé ({method}, code {result.get('code')})")
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
            # Créé directement en 0600 : pas d'instant où le jeton serait lisible par d'autres.
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
                pass  # session déjà fermée (partage coupé par l'utilisateur)


class CaptureService:
    """Flux continu de la fenêtre partagée ; `grab()` renvoie la dernière image reçue."""

    SOURCES = {"window": SOURCE_WINDOW, "monitor": SOURCE_MONITOR, "both": SOURCE_WINDOW | SOURCE_MONITOR}

    def __init__(self, on_state: Callable[[bool, str, bool], None], source: str = "window") -> None:
        # Appelé depuis le thread GLib : (flux actif ?, message, coupé en cours de route ?)
        self._on_state = on_state
        self._source_types = self.SOURCES[source]
        self._lock = threading.Lock()
        self._latest: Gst.Sample | None = None
        self._alive = False
        self._thread: threading.Thread | None = None
        self._loop: GLib.MainLoop | None = None
        self._pipeline: Gst.Pipeline | None = None
        self._portal: _Portal | None = None
        Gst.init(None)

    @property
    def alive(self) -> bool:
        return self._alive

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="glib-capture", daemon=True)
        self._thread.start()

    def restart(self, forget_window: bool = False) -> None:
        """Relance le partage ; avec forget_window, oublie la fenêtre mémorisée et rouvre le sélecteur GNOME."""
        self.stop()
        if forget_window:
            TOKEN_FILE.unlink(missing_ok=True)
        self.start()

    def stop(self) -> None:
        if self._loop:
            # La demande doit passer par le contexte GLib du thread de capture : GLib.idle_add()
            # viserait le contexte par défaut, que personne ne fait tourner.
            source = GLib.idle_source_new()
            source.set_callback(lambda *_: self._shutdown())
            source.attach(self._loop.get_context())
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = self._pipeline = self._portal = None

    def _shutdown(self) -> bool:
        if self._pipeline:
            self._pipeline.set_state(Gst.State.NULL)
        if self._portal:
            self._portal.close()
        if self._loop:
            self._loop.quit()
        return False

    def _run(self) -> None:
        ctx = GLib.MainContext.new()
        ctx.push_thread_default()
        try:
            self._loop = GLib.MainLoop.new(ctx, False)
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
            self._set_alive(True, "partage d'écran actif")
            self._loop.run()
        except Exception as exc:  # portail refusé, PipeWire absent…
            self._set_alive(False, f"capture indisponible : {exc}")
        finally:
            if self._alive:
                self._set_alive(False, "partage d'écran arrêté")
            ctx.pop_thread_default()

    def _set_alive(self, alive: bool, message: str, interrupted: bool = False) -> None:
        with self._lock:
            self._alive = alive
            if not alive:
                self._latest = None  # ne jamais renvoyer une image périmée
        self._on_state(alive, message, interrupted)

    def _on_sample(self, sink) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        with self._lock:
            self._latest = sample
        return Gst.FlowReturn.OK

    def _on_error(self, _bus, msg) -> None:
        err, _dbg = msg.parse_error()
        self._set_alive(False, f"partage d'écran interrompu ({err.message})", interrupted=True)

    def grab(self) -> Image.Image:
        with self._lock:
            sample, alive = self._latest, self._alive
        if not alive:
            raise CaptureError("partage d'écran inactif : relance-le depuis le coach")
        if sample is None:
            raise CaptureError("aucune image reçue pour l'instant")
        caps = sample.get_caps().get_structure(0)
        width, height = caps.get_value("width"), caps.get_value("height")
        buf = sample.get_buffer()
        ok, info = buf.map(Gst.MapFlags.READ)
        if not ok:
            raise CaptureError("lecture du tampon vidéo impossible")
        try:
            stride = len(info.data) // height
            img = Image.frombuffer("RGBA", (width, height), bytes(info.data), "raw", "RGBA", stride, 1)
        finally:
            buf.unmap(info)
        return img.convert("RGB")


def apply_crop_and_masks(img: Image.Image, crop: list[float], masks: list[list[float]]) -> Image.Image:
    """Recadre (fractions [g, h, d, b]) puis noircit les zones masquées (fractions de la zone recadrée)."""
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
    """Ne garde que les `keep` captures les plus récentes (noms horodatés). Renvoie le nombre supprimé."""
    files = sorted(directory.glob("capture-*.png"))
    old = files[:-keep] if keep else []
    for f in old:
        f.unlink(missing_ok=True)
        f.with_suffix(".json").unlink(missing_ok=True)  # journal du mode débogage
    logs = sorted(directory.glob("capture-*.json"))  # journaux sans image (copie des captures coupée)
    for f in logs[:-keep] if keep else []:
        f.unlink(missing_ok=True)
    return len(old)
