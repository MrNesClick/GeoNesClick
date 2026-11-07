import tomllib

import pytest
from fastapi.testclient import TestClient

from geonesclick.config import load_config
from geonesclick.server import create_app
from geonesclick.settings import SettingsError, current, save

ORIGIN = {"Origin": "http://localhost:1420"}


def test_save_merges_into_existing_user_file(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('[vision]\nmodel = "a/b"\n\n[capture]\ncrop = [0.0, 0.1, 1.0, 1.0]\n')
    cfg = save({"coach": {"default_level": 2}}, user)
    assert cfg.coach.default_level == 2
    written = tomllib.loads(user.read_text())
    assert written["vision"]["model"] == "a/b"  # clé existante conservée
    assert written["capture"]["crop"] == [0.0, 0.1, 1.0, 1.0]  # même hors de l'écran Réglages
    assert not (tmp_path / "config.tmp").exists()  # écriture atomique terminée


@pytest.mark.parametrize(
    "changes",
    [
        {"vision": {"base_url": "https://attaquant.example/v1"}},  # rediriger la clé API : interdit
        {"vision": {"api_key_env": "AUTRE"}},
        {"server": {"port": 1}},
        {"inconnue": {"x": 1}},
    ],
)
def test_non_editable_settings_are_refused(tmp_path, changes):
    user = tmp_path / "config.toml"
    with pytest.raises(SettingsError):
        save(changes, user)
    assert not user.exists()  # rien n'est écrit


def test_invalid_value_is_refused_without_writing(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('[coach]\ndefault_level = 1\n')
    with pytest.raises(SettingsError, match="default_level"):
        save({"coach": {"default_level": 7}}, user)
    assert tomllib.loads(user.read_text())["coach"]["default_level"] == 1


def test_current_exposes_only_editable_settings(tmp_path):
    cur = current(load_config(tmp_path / "absent.toml"))
    assert "base_url" not in cur["vision"] and cur["vision"]["model"]


@pytest.fixture
def client(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("[capture]\nnotify = false\n\n[vision]\nenabled = false\n")
    app = create_app(load_config(user), settings_path=user)
    return TestClient(app, base_url="http://127.0.0.1:47615"), app.state.engine, user


def test_settings_route_applies_live(client):
    http, engine, user = client
    res = http.post("/settings", json={"coach": {"reveal_countries": True}, "metas": {"max_categories": 2}},
                    headers=ORIGIN)
    assert res.status_code == 200
    assert engine.cfg.coach.reveal_countries is True and engine.cfg.metas.max_categories == 2
    assert tomllib.loads(user.read_text())["coach"]["reveal_countries"] is True


def test_settings_route_rejects_base_url(client):
    http, engine, _ = client
    res = http.post("/settings", json={"vision": {"base_url": "https://attaquant.example"}}, headers=ORIGIN)
    assert res.status_code == 422
    assert engine.cfg.vision.base_url.startswith("https://integrate.api.nvidia.com")


def test_foreign_origin_cannot_change_settings(client):
    http, *_ = client
    res = http.post("/settings", json={"coach": {"default_level": 2}}, headers={"Origin": "https://x.example"})
    assert res.status_code == 403


@pytest.mark.parametrize("model", ["../../etc", "a b/c", "x" * 200, "sans-slash"])
def test_model_test_rejects_malformed_ids(client, model):
    http, *_ = client
    assert http.post("/models/test", json={"model": model}, headers=ORIGIN).status_code == 422


def test_save_keeps_comments_and_layout(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('# mon commentaire\n[coach]\ndefault_level = 1  # je préfère chercher\n')
    save({"coach": {"default_level": 2}}, user)
    text = user.read_text()
    assert text.startswith("# mon commentaire\n")
    assert "default_level = 2  # je préfère chercher" in text


def test_save_only_writes_values_that_change(tmp_path):
    user = tmp_path / "config.toml"
    defaults = current(load_config(tmp_path / "absent.toml"))
    save(defaults | {"coach": {"default_level": 2, "reveal_countries": False}}, user)
    written = tomllib.loads(user.read_text())
    assert written == {"coach": {"default_level": 2}}  # le reste suit toujours les valeurs par défaut


def test_unreadable_user_file_is_refused_without_writing(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("coach = 3\n")
    with pytest.raises(SettingsError):
        save({"coach": {"default_level": 2}}, user)
    assert user.read_text() == "coach = 3\n"
