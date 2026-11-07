"""Le moteur ne doit répondre qu'à la fenêtre du coach, jamais à un site web ouvert dans le navigateur.

Le TestClient est utilisé sans bloc `with` : la phase de démarrage (partage d'écran, StreetCLIP) n'est
pas lancée, seules les règles d'accès HTTP et WebSocket sont testées.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from geonesclick.config import load_config
from geonesclick.server import create_app

APP_ORIGIN = "http://localhost:1420"
EVIL_ORIGIN = "https://site-malveillant.example"
WS_URL = "ws://127.0.0.1:47615/ws"  # URL complète : le client de test ignore base_url pour les WebSockets


@pytest.fixture
def client(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("[capture]\nnotify = false\n\n[vision]\nenabled = false\n")
    return TestClient(create_app(load_config(user)), base_url="http://127.0.0.1:47615")


@pytest.mark.parametrize("path", ["/capture", "/capture/restart", "/capture/reselect"])
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
    """Défense contre le DNS rebinding : la requête arrive sur 127.0.0.1 mais avec le Host du domaine piégé."""
    assert client.get("/health", headers={"Host": "piege.example:47615"}).status_code == 400


def test_cors_preflight_allowed_for_app_only(client):
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    ok = client.options("/label", headers={"Origin": APP_ORIGIN, **pre})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == APP_ORIGIN
    assert client.options("/label", headers={"Origin": EVIL_ORIGIN, **pre}).status_code == 403
