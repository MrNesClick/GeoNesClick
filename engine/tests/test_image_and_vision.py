import pytest
from PIL import Image

from geonesclick.capture import apply_crop_and_masks
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


def test_parse_fiche_ignores_surrounding_text():
    text = 'Voici la fiche :\n```json\n{"relief": "plat", "poteaux": ["bois"]}\n```\nBonne partie !'
    assert parse_fiche(text) == {"relief": "plat", "poteaux": ["bois"]}


@pytest.mark.parametrize("text", ["", "pas de json ici", "{ cassé", "} à l'envers {"])
def test_parse_fiche_rejects_unreadable(text):
    with pytest.raises(VisionError, match="unreadable"):
        parse_fiche(text)

