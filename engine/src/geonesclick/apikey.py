"""API key of the vision model, outside the repository: ~/.config/geonesclick/<name>.key, readable by you only (0600).

Decided with the user on 2026-11-07 ("API key not in the .env"; protected file preferred over the system
keyring). Reading order: the environment variable (tests, advanced uses), then the file. Entered from
Settings › Analysis; the UI only ever sees its last 4 characters. The repository's old .env is migrated
once at startup: the key is MOVED to the file, then its line removed from the .env (the rest is kept).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .i18n import t
from . import paths

NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")  # name of the variable ("NVAPI"): also used as the file name
VALUE = re.compile(r"[\x21-\x7e]{8,300}")  # printable characters, no space or line break


class ApiKeyError(ValueError):
    pass


def key_file(name: str) -> Path:
    if not NAME.fullmatch(name):
        raise ApiKeyError(t("apikey.bad_name", name=repr(name)))
    return paths.CONFIG_DIR / f"{name.lower()}.key"


def _write_private(path: Path, text: str) -> None:
    """Atomic write of a file readable by you only (created directly as 0600, never visible otherwise)."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read(name: str) -> str | None:
    if value := os.environ.get(name):
        return value
    path = key_file(name)
    try:
        value = path.read_text().strip()
    except OSError:
        return None
    return value or None


def save(name: str, value: str) -> None:
    value = value.strip()
    if not VALUE.fullmatch(value):
        raise ApiKeyError(t("apikey.bad_key"))
    if name == "NVAPI" and not value.startswith("nvapi-"):
        raise ApiKeyError(t("apikey.bad_nvidia"))
    _write_private(key_file(name), value + "\n")


def forget(name: str) -> None:
    key_file(name).unlink(missing_ok=True)


def hint(name: str) -> dict[str, str] | None:
    """What the UI may show: where the key comes from and its last 4 characters, never the key."""
    value = read(name)
    if not value:
        return None
    return {"source": "env" if os.environ.get(name) else "file", "end": value[-4:]}  # shown via settings.key_source.*


def migrate_env(name: str, env_file: Path) -> bool:
    """The repository's old .env: the key is moved to the protected file, then its line removed from the .env."""
    if not env_file.is_file() or key_file(name).exists():
        return False
    lines = env_file.read_text().splitlines(keepends=True)
    found = [ln.partition("=")[2].strip().strip("\"'") for ln in lines if ln.partition("=")[0].strip() == name]
    if not found or not found[-1]:
        return False
    save(name, found[-1])  # first the protected copy…
    kept = "".join(ln for ln in lines if ln.partition("=")[0].strip() != name)
    _write_private(env_file, kept)  # … only then the line removed
    return True


def main() -> int:
    """python -m geonesclick.apikey < key: saves the key read from standard input (never as an argument, visible
    to the machine's other programs). Called by the first-launch assistant."""
    import sys

    from .config import load_config

    try:
        save(load_config().vision.api_key_env, sys.stdin.readline())
    except ApiKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
