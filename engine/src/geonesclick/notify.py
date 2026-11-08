"""GNOME notifications (org.freedesktop.Notifications): capture confirmation or error."""

from __future__ import annotations

import threading
from pathlib import Path

from gi.repository import Gio, GLib


class Notifier:
    """Each notification replaces the previous one and stays "transient" (no build-up)."""

    def __init__(self, enabled: bool, sound: bool) -> None:
        self.enabled = enabled
        self.sound = sound
        self._last_id = 0
        self._lock = threading.Lock()
        self._bus: Gio.DBusConnection | None = None  # opened on the first notification: no session bus, no crash

    def _session_bus(self) -> Gio.DBusConnection | None:
        if self._bus is None:
            try:
                self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            except GLib.Error as exc:  # no graphical session (SSH, CI): notifications are skipped, retried next time
                print(f"[notification] pas de bus de session : {exc.message}")
        return self._bus

    def send(self, summary: str, body: str = "", image: Path | None = None, error: bool = False) -> None:
        if not self.enabled:
            return
        hints = {"transient": GLib.Variant("b", True), "urgency": GLib.Variant("y", 2 if error else 1)}
        if image is not None:
            hints["image-path"] = GLib.Variant("s", str(image))
        if self.sound:
            hints["sound-name"] = GLib.Variant("s", "dialog-error" if error else "camera-shutter")
        icon = "dialog-error-symbolic" if error else "camera-photo-symbolic"
        with self._lock:
            bus = self._session_bus()
            if bus is None:
                return
            try:
                reply = bus.call_sync(
                    "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                    "org.freedesktop.Notifications", "Notify",
                    GLib.Variant("(susssasa{sv}i)", (
                        "GeoNesClick", self._last_id, icon, summary, body, [], hints,
                        8000 if error else 2000,
                    )),
                    GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 2000, None,
                )
                self._last_id = reply.unpack()[0]
            except GLib.Error as exc:  # a failed notification must never block the capture
                print(f"[notification] échec : {exc.message}")
