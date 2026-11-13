"""Is a newer GeoNesClick out? Asks GitHub's latest release, at most once a day, if [updates] check is on.

Only the version number is read; nothing is downloaded or installed: the coach shows a banner (closed once per
version) and Settings shows the version available, with a button that opens the release page. What leaves the
machine: the IP address and the app's version (User-Agent), like any web page. The state is kept in
updates.json: when it last checked, the latest version seen, the version whose banner was closed.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

FILE = "updates.json"
REPO = "MrNesClick/GeoNesClick"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/v{{version}}"
EVERY = timedelta(days=1)
TIMEOUT_S = 10
MAX_BYTES = 1_000_000  # the answer is a few kB; a bigger one is not GitHub's
VERSION = re.compile(r"\d{1,4}\.\d{1,4}\.\d{1,4}")


def current() -> str:
    try:
        return version("geonesclick")
    except PackageNotFoundError:  # run from the sources without installing: never claims an update
        return "0.0.0"


def newer(candidate: str, than: str) -> bool:
    """Is `candidate` a newer release than `than`? Only plain x.y.z numbers compare."""
    if not (VERSION.fullmatch(candidate) and VERSION.fullmatch(than)):
        return False
    return tuple(map(int, candidate.split("."))) > tuple(map(int, than.split(".")))


def fetch_latest() -> str:
    """The latest release's version, from its tag ("v0.5.1" → "0.5.1"). Raises OSError / ValueError when GitHub does
    not answer or answers something else."""
    request = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"GeoNesClick/{current()} (update check; https://github.com/{REPO})",
    })
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as answer:
        body = answer.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("answer too large")
    tag = str(json.loads(body).get("tag_name", ""))
    found = tag.removeprefix("v")
    if not VERSION.fullmatch(found):
        raise ValueError(f"unexpected tag: {tag[:40]!r}")
    return found


class Updates:
    def __init__(self, file: Path) -> None:
        self.file = file
        self.state: dict[str, Any] = {}
        try:
            loaded = json.loads(file.read_text())
            self.state = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            pass  # first check, or a damaged file: starts again
        self.error = ""

    def _save(self) -> None:
        tmp = self.file.with_suffix(".tmp")
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.state))
            tmp.replace(self.file)
        except OSError:
            pass  # disk full, folder forbidden: asked again at the next start

    def due(self, now: datetime | None = None) -> bool:
        try:
            last = datetime.fromisoformat(str(self.state.get("checked", "")))
        except ValueError:
            return True
        return (now or datetime.now()) - last >= EVERY

    def check(self) -> None:
        """Asks GitHub now (blocking: run it in a thread)."""
        try:
            self.state["latest"] = fetch_latest()
            self.error = ""
        except (OSError, ValueError) as exc:  # offline, GitHub down, rate limit (403), no release yet (404)
            self.error = str(exc)[:200]
        self.state["checked"] = datetime.now().isoformat(timespec="seconds")
        self._save()

    def dismiss(self, version: str) -> None:
        """The banner of this version was closed: it does not come back (a newer version brings it back once)."""
        if VERSION.fullmatch(version):
            self.state["dismissed"] = version
            self._save()

    def status(self, enabled: bool) -> dict[str, Any]:
        latest = str(self.state.get("latest", ""))
        available = newer(latest, current())
        return {
            "enabled": enabled,
            "current": current(),
            "latest": latest if available else "",
            "url": RELEASE_PAGE.format(version=latest) if available else "",
            "dismissed": self.state.get("dismissed") == latest,
            "checked": self.state.get("checked", ""),
            "error": self.error,
        }
