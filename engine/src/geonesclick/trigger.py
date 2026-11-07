"""Commandes des raccourcis GNOME : python -m geonesclick.trigger [capture|mark]

capture (par défaut) analyse la vue ; mark la fige en plein écran pour y entourer des indices (marques).
"""

from __future__ import annotations

import socket
import sys

from .paths import SOCKET_PATH


COMMANDS = ("capture", "mark")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else "capture"
    if cmd not in COMMANDS:
        print(f"Commande inconnue : {cmd} (attendu : {', '.join(COMMANDS)})", file=sys.stderr)
        return 2
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect(str(SOCKET_PATH))
            s.sendall(cmd.encode() + b"\n")
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
