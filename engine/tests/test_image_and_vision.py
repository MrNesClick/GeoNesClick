import pytest
from PIL import Image

from geonesclick.capture import apply_crop_and_masks, trim_padding
from geonesclick.vision import VisionError, parse_fiche


def test_crop_uses_fractions():
    img = Image.new("RGB", (200, 100), (255, 255, 255))
    out = apply_crop_and_masks(img, [0.5, 0.0, 1.0, 0.5], [])
    assert out.size == (100, 50)


def test_masks_are_relative_to_the_cropped_view():
    img = Image.new("RGB", (200, 100), (255, 255, 255))
    out = apply_crop_and_masks(img, [0.5, 0.0, 1.0, 1.0], [[0.5, 0.5, 1.0, 1.0]])
    assert out.getpixel((99, 99)) == (0, 0, 0)  # bottom-right corner masked
    assert out.getpixel((10, 10)) == (255, 255, 255)
    assert img.getpixel((199, 99)) == (255, 255, 255)  # the original is not modified


def test_no_crop_no_mask_keeps_image():
    img = Image.new("RGB", (40, 30))
    assert apply_crop_and_masks(img, [], []).size == (40, 30)


def test_the_black_padding_of_a_window_shrunk_during_the_sharing_goes():
    stream = Image.new("RGB", (1920, 1200))  # the size the sharing started with, pure black
    stream.paste((90, 120, 60), (15, 10, 1038, 1168))  # the window, after its shadow, at the top left
    assert trim_padding(stream).size == (1023, 1158)


def test_a_frame_without_padding_or_black_all_over_stays_as_it_is():
    window = Image.new("RGB", (64, 40), (90, 120, 60))
    window.paste((0, 0, 0), (20, 10, 40, 30))  # black inside the view is not padding
    assert trim_padding(window) is window
    black = Image.new("RGB", (64, 40))
    assert trim_padding(black) is black


def test_parse_fiche_ignores_surrounding_text():
    text = 'Here is the sheet:\n```json\n{"relief": "flat", "poles": ["wood"]}\n```\nGood game!'
    assert parse_fiche(text) == {"relief": "flat", "poles": ["wood"]}


@pytest.mark.parametrize("text", ["", "no json here", "{ broken", "} reversed {"])
def test_parse_fiche_rejects_unreadable(text):
    with pytest.raises(VisionError, match="unreadable"):
        parse_fiche(text)



def test_prompts_get_the_ui_language_and_keep_their_json_braces():
    from geonesclick import i18n
    from geonesclick.vision import with_language

    prompt = 'Answer {"a": 1} in {language}.'
    assert with_language(prompt) == 'Answer {"a": 1} in English.'
    i18n.set_language("fr")
    assert with_language(prompt) == 'Answer {"a": 1} in français.'
    i18n.set_language("es")  # no Spanish catalog: the UI, and the AI's answers shown in it, stay English
    assert with_language(prompt) == 'Answer {"a": 1} in English.'
