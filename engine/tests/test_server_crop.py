"""The browser's bars (tab titles, address, bookmarks) never reach the models or the NVIDIA API."""

import asyncio

import numpy as np
from PIL import Image

from geonesclick.config import load_config
from geonesclick.pagetop import DEFAULT_SHARE, PageTop
from geonesclick.server import create_app
from geonesclick.streetclip import CountryScore

W, H, BARS = 400, 300, 30  # the bars fit in the default share, as Chrome's 121 px in 1200


BAR_PIXELS = np.random.default_rng(0).integers(230, 256, (BARS, W, 3), dtype=np.uint8)


def window(seed: int) -> Image.Image:
    """A window whose bars (the same in every round) end on no plain line: the first capture cannot tell."""
    a = np.random.default_rng(seed).integers(0, 200, (H, W, 3), dtype=np.uint8)
    a[:BARS] = BAR_PIXELS
    return Image.fromarray(a)


class FakeClip:
    device = "cpu"

    def __init__(self):
        self.seen = []

    def analyse(self, img):
        self.seen.append(img)
        return [CountryScore("Hungary", "HU", 0.7)], 5.0, None, None


class FakeVision:
    ready, client = True, None

    def __init__(self):
        self.seen = []

    async def describe(self, img):
        self.seen.append(img)
        return {}, 0.1


def analysed(tmp_path, settings: str = "") -> tuple[FakeClip, FakeVision, list[dict]]:
    user = tmp_path / "config.toml"
    user.write_text(f'[capture]\nnotify = false\nsave_to_disk = false\n{settings}')
    engine = create_app(load_config(user), user).state.engine
    engine.page_top = PageTop(tmp_path / "page-top.json")
    frames = iter([window(1), window(2)])
    engine.capture.grab = lambda: next(frames)
    engine.streetclip, engine.vision = FakeClip(), FakeVision()
    sent = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast

    async def run():
        for _ in range(2):
            await engine.analyse()
            await asyncio.gather(*engine.background)

    asyncio.run(run())
    return engine.streetclip, engine.vision, [m for m in sent if m.get("type") == "capture"]


def has_bars(img: Image.Image) -> bool:
    return bool((np.asarray(img) >= 230).all(axis=(1, 2)).any())


def test_without_a_crop_set_the_bars_are_cut_from_the_first_capture_then_exactly(tmp_path):
    clip, vision, captures = analysed(tmp_path)
    assert [c["guessed_crop"] for c in captures] == [True, False]
    assert [img.height for img in vision.seen] == [H - round(H * DEFAULT_SHARE), H - BARS]
    assert not any(has_bars(img) for img in clip.seen + vision.seen)


def test_a_crop_set_by_hand_wins(tmp_path):
    clip, vision, captures = analysed(tmp_path, "crop = [0.0, 0.5, 1.0, 1.0]\n")
    assert [c["guessed_crop"] for c in captures] == [False, False]
    assert [img.height for img in clip.seen] == [H // 2, H // 2]
