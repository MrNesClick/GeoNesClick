"""Where the page starts in the shared window, below the browser's bars (tabs, address, bookmarks).

Two ways to find it, and the lowest edge wins, so that one of them going wrong upwards never lets a bar through:
- in the capture itself: the browser draws a plain line across the whole width under its bars (Chrome: found on the
  58 captures of the test set, within 3 px);
- from successive captures: the bars stay the same from one round to the next while the view changes, so comparing
  two captures of the same size, the rows at the top that did not change are the browser. The lowest edge found is
  kept per window size, in a file. This one knows nothing of the browser or its theme.
When neither finds anything, a fixed share of the height is cut (DEFAULT_SHARE), enough for Chrome's bars at scale 1
and at scale 2.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
from PIL import Image

FILE = "page-top.json"  # in the config folder: the learnt edge per window size
DEFAULT_SHARE = 0.12  # cut until the edge is known: 144 px at 1200 high, 259 px at 2160
MAX_SHARE = 0.25  # the bars never take more; an edge found there means the two views are the same
STATIC_ROW = 0.6  # share of a row's pixels unchanged between two rounds for the row to belong to the bars
SAME_PIXEL = 3  # tolerance per channel (video compression)
PLAIN_ROW = 0.97  # share of a row's pixels of the same colour for the row to be the line under the bars
PLAIN_PIXEL = 2
STRIDE = 4  # one column out of 4 is enough to tell a plain row (a 4K top quarter stays fast)


def line_edge(top: np.ndarray) -> int | None:
    """Below the last plain row across the whole width in the top part of a capture, or None."""
    sample = top[:, ::STRIDE].astype(np.int16)
    median = np.median(sample, axis=1, keepdims=True)
    plain = (np.abs(sample - median).max(axis=2) <= PLAIN_PIXEL).mean(axis=1) >= PLAIN_ROW
    rows = np.flatnonzero(plain)
    return int(rows[-1]) + 1 if rows.size else None


def static_rows(previous: np.ndarray, current: np.ndarray) -> int:
    """Number of rows at the top that are the same in both images (top parts of the same size)."""
    same = (np.abs(previous.astype(np.int16) - current.astype(np.int16)).max(axis=2) <= SAME_PIXEL).mean(axis=1)
    changed = np.flatnonzero(same < STATIC_ROW)
    return int(changed[0]) if changed.size else len(same)


class PageTop:
    """Learns the page's top edge per window size from successive captures, and crops the bars off."""

    def __init__(self, file: Path) -> None:
        self.file = file
        self._lock = threading.Lock()
        self._previous: tuple[tuple[int, int], np.ndarray] | None = None
        self._line: tuple[tuple[int, int], int | None] | None = None  # the line found in the last capture
        try:
            saved = json.loads(file.read_text())
            self._edges = {k: v for k, v in saved.items() if type(v) is int and v >= 0}
        except (OSError, ValueError, AttributeError):
            self._edges = {}

    @staticmethod
    def _key(size: tuple[int, int]) -> str:
        return f"{size[0]}x{size[1]}"

    def learn(self, frame: Image.Image) -> None:
        """Looks for the line under the bars in the frame, and compares the frame with the previous one of the same
        size, keeping the lowest edge found per size."""
        limit = int(frame.height * MAX_SHARE)
        top = np.asarray(frame.crop((0, 0, frame.width, limit)).convert("RGB"))  # the top only: no 4K copy
        line = line_edge(top)
        with self._lock:
            self._line = (frame.size, line if line and line < limit else None)
            previous, self._previous = self._previous, (frame.size, top)
            if previous is None or previous[0] != frame.size:
                return
            edge = static_rows(previous[1], top)
            key = self._key(frame.size)
            if 0 < edge < limit and edge > self._edges.get(key, 0):
                self._edges[key] = edge
                self._save()

    def _save(self) -> None:
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._edges))
            tmp.replace(self.file)
        except OSError:
            pass  # kept in memory for this session

    def crop(self, frame: Image.Image) -> tuple[Image.Image, bool]:
        """The frame (passed to learn() first) without the browser's bars, and whether the edge was a guess."""
        with self._lock:
            found = [self._edges.get(self._key(frame.size))]
            if self._line and self._line[0] == frame.size:
                found.append(self._line[1])
        found = [edge for edge in found if edge]
        guessed = not found
        edge = round(frame.height * DEFAULT_SHARE) if guessed else max(found)
        return frame.crop((0, edge, frame.width, frame.height)), guessed
