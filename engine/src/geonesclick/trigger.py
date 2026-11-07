"""Déclenche une capture (commande du raccourci GNOME) : python -m geonesclick.trigger"""

from __future__ import annotations

import socket
import sys

from .paths import SOCKET_PATH


def main() -> int:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect(str(SOCKET_PATH))
            s.sendall(b"capture\n")
            print(s.recv(4096).decode().strip())
        return 0
    except (FileNotFoundError, ConnectionRefusedError):
        from .notify import Notifier  # import tardif : évite de charger GLib quand tout va bien

        Notifier(enabled=True, sound=True).send(
            "Coach non lancé", "Ouvre l'application GeoNesClick avant de capturer.", error=True
        )
        print("Le coach n'est pas lancé.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
