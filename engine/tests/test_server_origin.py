"""The engine must only answer the coach window, never a website open in the browser.

The TestClient is used without a `with` block: the startup phase (screen sharing, StreetCLIP) is not
run, only the HTTP and WebSocket access rules are tested.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from geonesclick.config import load_config
from geonesclick.server import create_app

APP_ORIGIN = "http://localhost:1420"
EVIL_ORIGIN = "https://site-malveillant.example"
WS_URL = "ws://127.0.0.1:47615/ws"  # full URL: the test client ignores base_url for WebSockets


@pytest.fixture
def client(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("[capture]\nnotify = false\n\n[vision]\nenabled = false\n")
    return TestClient(create_app(load_config(user)), base_url="http://127.0.0.1:47615")


@pytest.mark.parametrize("path", ["/capture", "/capture/reselect", "/capture/start"])
def test_foreign_origin_cannot_trigger_actions(client, path):
    assert client.post(path, headers={"Origin": EVIL_ORIGIN}).status_code == 403


def test_foreign_origin_cannot_read_state(client):
    assert client.get("/health", headers={"Origin": EVIL_ORIGIN}).status_code == 403


def test_app_origin_reads_state_with_cors_header(client):
    res = client.get("/health", headers={"Origin": APP_ORIGIN})
    assert res.status_code == 200
    assert res.json()["type"] == "state"
    assert res.headers["access-control-allow-origin"] == APP_ORIGIN


def test_websocket_rejects_foreign_origin(client):
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(WS_URL, headers={"Origin": EVIL_ORIGIN}) as ws:
        ws.receive_json()


def test_websocket_rejects_missing_origin(client):
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(WS_URL) as ws:
        ws.receive_json()


def test_websocket_sends_state_to_app(client):
    with client.websocket_connect(WS_URL, headers={"Origin": APP_ORIGIN}) as ws:
        assert ws.receive_json()["type"] == "state"


def test_foreign_host_is_rejected(client):
    """Defence against DNS rebinding: the request arrives on 127.0.0.1 but with the booby-trapped domain's Host."""
    assert client.get("/health", headers={"Host": "piege.example:47615"}).status_code == 400


def test_cors_preflight_allowed_for_app_only(client):
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    ok = client.options("/label", headers={"Origin": APP_ORIGIN, **pre})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == APP_ORIGIN
    assert client.options("/label", headers={"Origin": EVIL_ORIGIN, **pre}).status_code == 403


def test_restarting_the_sharing_reopens_the_gnome_picker(client):
    """A remembered window that no longer exists must not block the restart: the picker opens."""
    calls = []
    engine = client.app.state.engine
    engine.capture.restart = lambda forget_window=False: calls.append(forget_window)
    assert client.post("/capture/reselect", headers={"Origin": APP_ORIGIN}).status_code == 200
    assert calls == [True]
    assert client.post("/capture/restart", headers={"Origin": APP_ORIGIN}).status_code in (404, 405)  # route removed


def test_nothing_is_shared_until_the_player_shares_the_game_window(client):
    """The coach open is not a consent to share a window: the start shares nothing; the button resumes the remembered
    window (no dialog), unlike "Restart sharing" which reopens the picker."""
    import asyncio

    engine = client.app.state.engine
    started, restarts = [], []
    engine.capture.start = lambda: started.append(True)
    engine.capture.restart = lambda forget_window=False: restarts.append(forget_window)
    engine.cfg.streetclip.enabled = engine.cfg.plonk.enabled = engine.cfg.plonkit.enabled = False
    engine.cfg.rules.places = engine.cfg.updates.check = False
    asyncio.run(engine.start())
    state = engine.state()["capture"]
    assert started == [] and (state["alive"], state["starting"], state["idle"]) == (False, False, True)
    assert client.post("/capture/start", headers={"Origin": APP_ORIGIN}).status_code == 200
    assert restarts == [False]  # the remembered window is kept
    assert engine.state()["capture"]["idle"] is False
