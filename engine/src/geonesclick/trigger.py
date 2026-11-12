"""GNOME shortcut commands: python -m geonesclick.trigger [capture|mark]

capture (default) analyses the view; mark freezes it in full screen to circle clues on it (marks).
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
        print(f"Unknown command: {cmd} (expected: {', '.join(COMMANDS)})", file=sys.stderr)
        return 2
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect(str(SOCKET_PATH))
            s.sendall(cmd.encode() + b"\n")
            print(s.recv(4096).decode().strip())
        return 0
    except (FileNotFoundError, ConnectionRefusedError):
        from .config import load_config  # late imports: avoid loading GLib and the config when all is well
        from .i18n import set_language, t
        from .notify import Notifier

        try:
            set_language(load_config().coach.language)
        except Exception:  # an unreadable config must not hide the notification: English then
            pass
        Notifier(enabled=True, sound=True).send(t("trigger.not_running.title"), t("trigger.not_running.body"), error=True)
        print("The coach is not running.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
