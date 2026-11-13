"""Where the page starts below the browser's bars, learnt from successive captures."""

import json

import numpy as np
from PIL import Image

from geonesclick.pagetop import DEFAULT_SHARE, PageTop

W, H, BARS = 400, 300, 40


BAR_PIXELS = np.random.default_rng(0).integers(200, 256, (H, 600, 3), dtype=np.uint8)  # the same in every round


def window(seed: int, bars: int = BARS, size: tuple[int, int] = (W, H), line: bool = False) -> Image.Image:
    """A browser window: the same bars on top, then a view that changes with each round. With `line`, the browser
    draws a plain line under its bars (Chrome); without, nothing in one capture tells where they end."""
    w, h = size
    a = np.random.default_rng(seed).integers(0, 200, (h, w, 3), dtype=np.uint8)
    a[:bars] = BAR_PIXELS[:bars, :w]
    if line:
        a[bars - 1] = 180
    return Image.fromarray(a)


def is_bar(img: Image.Image) -> bool:
    """The first row of the image is still the browser's."""
    return bool((np.asarray(img)[0] >= 180).all())


def test_the_line_under_the_bars_gives_the_edge_from_the_first_capture(tmp_path):
    pages = PageTop(tmp_path / "page-top.json")
    first = window(1, line=True)
    pages.learn(first)
    page, guessed = pages.crop(first)
    assert not guessed and page.height == H - BARS and not is_bar(page)


def test_a_line_found_too_high_never_lets_the_learnt_bars_through(tmp_path):
    pages = PageTop(tmp_path / "page-top.json")
    pages.learn(window(1))
    pages.learn(window(2))  # learnt: 40
    a = np.array(window(3))
    a[20] = 180  # a plain row inside the bars (between two of them): the line found is higher than the edge
    pages.learn(Image.fromarray(a))
    page, _ = pages.crop(Image.fromarray(a))
    assert page.height == H - BARS


def test_without_a_line_cuts_a_share_of_the_height_until_two_captures_were_compared(tmp_path):
    pages = PageTop(tmp_path / "page-top.json")
    pages.learn(window(1))
    page, guessed = pages.crop(window(1))
    assert guessed and page.height == H - round(H * DEFAULT_SHARE)


def test_then_cuts_exactly_where_the_page_starts(tmp_path):
    pages = PageTop(tmp_path / "page-top.json")
    for seed in (1, 2):
        pages.learn(window(seed))
    page, guessed = pages.crop(window(2))
    assert not guessed and page.height == H - BARS and not is_bar(page)


def test_keeps_the_lowest_edge_when_the_bars_changed_between_two_rounds(tmp_path):
    pages = PageTop(tmp_path / "page-top.json")
    pages.learn(window(1))
    pages.learn(window(2))
    pages.learn(window(3, bars=60))  # a bar appeared: this comparison still finds 40, the next one 60
    pages.learn(window(4, bars=60))
    pages.learn(window(5))  # the bar went away: 40 found again, 60 is kept (a bar never leaves with the view)
    page, _ = pages.crop(window(5))
    assert page.height == H - 60


def test_the_same_view_twice_teaches_nothing(tmp_path):
    pages = PageTop(tmp_path / "page-top.json")
    pages.learn(window(1))
    pages.learn(window(1))
    assert pages.crop(window(1))[1]


def test_the_edge_is_kept_per_window_size_and_across_restarts(tmp_path):
    file = tmp_path / "page-top.json"
    pages = PageTop(file)
    pages.learn(window(1))
    pages.learn(window(2))
    assert json.loads(file.read_text()) == {f"{W}x{H}": BARS}
    again = PageTop(file)
    assert not again.crop(window(3))[1]
    assert again.crop(window(3, size=(500, 300)))[1]  # another size: not learnt yet


def test_a_damaged_file_is_ignored(tmp_path):
    file = tmp_path / "page-top.json"
    file.write_text('{"400x300": "x", "500x300": -3')
    assert PageTop(file).crop(window(1))[1]
