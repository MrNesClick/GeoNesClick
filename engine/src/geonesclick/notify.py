"""Notifications GNOME (org.freedesktop.Notifications) : confirmation de capture ou erreur."""

from __future__ import annotations

import threading
from pathlib import Path

from gi.repository import Gio, GLib


class Notifier:
    """Chaque notification remplace la précédente et reste « transient » (pas d'accumulation)."""

    def __init__(self, enabled: bool, sound: bool) -> None:
        self.enabled = enabled
        self.sound = sound
        self._last_id = 0
        self._lock = threading.Lock()
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)  # ouvert même désactivé : réactivable à chaud

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
            try:
                reply = self._bus.call_sync(
                    "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                    "org.freedesktop.Notifications", "Notify",
                    GLib.Variant("(susssasa{sv}i)", (
                        "GeoNesClick", self._last_id, icon, summary, body, [], hints,
                        8000 if error else 2000,
                    )),
                    GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 2000, None,
                )
                self._last_id = reply.unpack()[0]
            except GLib.Error as exc:  # une notification ratée ne doit jamais bloquer la capture
                print(f"[notification] échec : {exc.message}")
