"""Lecture des pages Plonk It : données synthétiques uniquement (aucun contenu de Plonk It dans le dépôt)."""

import json

import pytest

from geonesclick.plonkit import PlonkitError, extract_guide, parse_guide_list, tips_of

GUIDE = {
    "slug": "testland", "code": "tl", "title": "Testland",
    "steps": [
        {"kind": "steps", "title": "Identifying Testland", "items": [
            {"kind": "centeredImage", "id": "a", "imageUrl": "/x.png"},
            {"kind": "tip", "id": "b", "data": {
                "text": ["Poles **with holes**.", "Second paragraph."],
                "image": {"imageUrl": "/images/t/p.png", "imageLink": "https://maps.example/sv"}}},
            {"kind": "tip", "id": "c", "tags": ["bollard"], "data": {"text": "Bollards."}},
        ]},
    ],
}


def page(guide):
    return f'<html><script id="__PRELOADED_DATA__" type="application/json">{json.dumps({"success": True, "data": {"public": guide}})}</script></html>'


def test_tips_are_extracted_with_their_section_and_image():
    tips = tips_of(extract_guide(page(GUIDE)))
    assert [t.tip_id for t in tips] == ["b", "c"]
    assert tips[0].text == "Poles **with holes**.\n\nSecond paragraph."
    assert (tips[0].country, tips[0].section, tips[0].image_url) == ("TL", "Identifying Testland", "/images/t/p.png")
    assert tips[1].tags == ["bollard"] and tips[1].url == "https://www.plonkit.net/testland"


def test_page_without_preloaded_data_is_an_error():
    with pytest.raises(PlonkitError, match="introuvable"):
        extract_guide("<html></html>")


@pytest.mark.parametrize("slug", ["../etc", "a/b", "", "UPPER", "x" * 80])
def test_unsafe_slugs_are_dropped_from_the_list(slug):
    payload = json.dumps({"success": True, "data": [
        {"slug": slug, "code": "SE", "title": "x", "updatedAt": "d"},
        {"slug": "sweden", "code": "se", "title": "Sweden", "updatedAt": "d"},
    ]}).encode()
    assert [r.slug for r in parse_guide_list(payload)] == ["sweden"]


def test_collect_stops_on_429(tmp_path, monkeypatch):
    import urllib.error

    from geonesclick import plonkit

    listing = json.dumps({"success": True, "data": [
        {"slug": "sweden", "code": "SE", "title": "Sweden", "updatedAt": "d"},
        {"slug": "norway", "code": "NO", "title": "Norway", "updatedAt": "d"}]}).encode()
    calls = []

    def fake_get(url, timeout=20.0):
        calls.append(url)
        if url.endswith("/api/guides"):
            return listing
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {"Retry-After": "60"}, None)

    monkeypatch.setattr(plonkit, "_get", fake_get)
    monkeypatch.setattr(plonkit.time, "sleep", lambda _s: None)
    with pytest.raises(PlonkitError, match="429"):
        plonkit.collect(None, tmp_path, delay_s=1.0)
    assert len(calls) == 2  # la liste, puis une seule page : on n'insiste pas


def test_classification_prefers_tags_then_keywords():
    from geonesclick.plonkit_index import DEFAULT_KEYWORDS, _keyword_patterns, classify

    patterns = _keyword_patterns(DEFAULT_KEYWORDS)
    assert classify("Anything", ["pole"], patterns) == ("poteaux", "etiquette")
    assert classify("Black and white **bollards** with a reflector", [], patterns) == ("bornes", "mots-cles")
    assert classify("Look at the .no domain on shops", [], patterns)[0] == "domaine"
    assert classify("Nothing useful here", [], patterns) == ("autre", "aucune")


def test_interrupted_collect_does_not_mark_the_check_done(tmp_path, monkeypatch):
    import urllib.error

    from geonesclick import plonkit

    listing = json.dumps({"success": True, "data": [{"slug": "sweden", "code": "SE", "title": "S", "updatedAt": "d"}]})

    def fake_get(url, timeout=20.0):
        if url.endswith("/api/guides"):
            return listing.encode()
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(plonkit, "_get", fake_get)
    monkeypatch.setattr(plonkit.time, "sleep", lambda _s: None)
    with pytest.raises(PlonkitError):
        plonkit.collect(None, tmp_path)
    assert not (tmp_path / plonkit.CHECKED_FILE).exists()
