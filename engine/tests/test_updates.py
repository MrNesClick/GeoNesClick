"""The update check: GitHub's latest release, at most once a day, a banner closed once per version."""

import io
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from geonesclick import updates
from geonesclick.config import load_config
from geonesclick.server import create_app
from geonesclick.updates import Updates, fetch_latest as real_fetch_latest, newer

ORIGIN = {"Origin": "http://localhost:1420"}


def test_only_a_higher_release_number_is_newer():
    assert newer("0.5.1", "0.5.0") and newer("0.10.0", "0.9.9") and newer("1.0.0", "0.99.99")
    assert not newer("0.5.0", "0.5.0") and not newer("0.4.9", "0.5.0")
    assert not newer("0.6.0-rc1", "0.5.0") and not newer("", "0.5.0")


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.mark.parametrize("body, found", [
    ({"tag_name": "v0.5.1", "body": "notes"}, "0.5.1"),
    ({"tag_name": "0.6.0"}, "0.6.0"),
])
def test_the_latest_version_is_read_from_the_release_tag(monkeypatch, body, found):
    seen = {}

    def urlopen(request, timeout):
        seen["url"], seen["agent"], seen["timeout"] = request.full_url, request.get_header("User-agent"), timeout
        return Answer(json.dumps(body).encode())

    monkeypatch.setattr(updates.urllib.request, "urlopen", urlopen)
    assert real_fetch_latest() == found
    assert seen["url"] == "https://api.github.com/repos/MrNesClick/GeoNesClick/releases/latest"
    assert seen["agent"].startswith("GeoNesClick/") and seen["timeout"] == updates.TIMEOUT_S


@pytest.mark.parametrize("body", [b'{"tag_name": "v1.0; rm -rf"}', b"not json", b'{"message": "Not Found"}',
                                  b"x" * (updates.MAX_BYTES + 1)])
def test_anything_but_a_release_number_is_refused(monkeypatch, body):
    monkeypatch.setattr(updates.urllib.request, "urlopen", lambda request, timeout: Answer(body))
    with pytest.raises(ValueError):
        real_fetch_latest()


def test_asked_at_most_once_a_day_and_a_failure_waits_too(tmp_path, monkeypatch):
    state = Updates(tmp_path / "updates.json")
    assert state.due()
    monkeypatch.setattr(updates, "fetch_latest", lambda: (_ for _ in ()).throw(OSError("offline")))
    state.check()
    assert not state.due() and state.error == "offline"  # GitHub is not asked again every hour when offline
    assert state.due(datetime.now() + timedelta(days=1, seconds=1))
    assert not Updates(tmp_path / "updates.json").due()  # kept across starts


def test_a_newer_version_is_offered_until_its_banner_is_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "current", lambda: "0.5.0")
    state = Updates(tmp_path / "updates.json")
    monkeypatch.setattr(updates, "fetch_latest", lambda: "0.5.1")
    state.check()
    shown = state.status(enabled=True)
    assert (shown["latest"], shown["dismissed"]) == ("0.5.1", False)
    assert shown["url"] == "https://github.com/MrNesClick/GeoNesClick/releases/tag/v0.5.1"
    state.dismiss("0.5.1")
    assert Updates(tmp_path / "updates.json").status(enabled=True)["dismissed"]  # never again for 0.5.1
    monkeypatch.setattr(updates, "fetch_latest", lambda: "0.5.2")
    state.check()
    assert state.status(enabled=True)["dismissed"] is False  # a newer one brings the banner back once
    monkeypatch.setattr(updates, "current", lambda: "0.5.2")
    assert state.status(enabled=True)["latest"] == ""  # installed: nothing to offer


def test_the_routes_check_on_demand_and_close_a_banner(tmp_path, monkeypatch):
    user = tmp_path / "config.toml"
    user.write_text("[updates]\ncheck = false\n")  # off: "Check now" still asks, the click is the consent
    app = create_app(load_config(user), user)
    monkeypatch.setattr(updates, "current", lambda: "0.5.0")
    monkeypatch.setattr(updates, "fetch_latest", lambda: "0.6.0")
    client = TestClient(app, base_url="http://127.0.0.1:47615")
    shown = client.post("/updates/check", headers=ORIGIN).json()
    assert (shown["enabled"], shown["latest"]) == (False, "0.6.0")
    assert client.post("/updates/dismiss", headers=ORIGIN, json={"version": "0.6.0"}).json() == {"ok": True}
    assert app.state.engine.state()["updates"]["dismissed"]
    assert client.post("/updates/dismiss", headers=ORIGIN, json={"version": "x" * 21}).status_code == 422
