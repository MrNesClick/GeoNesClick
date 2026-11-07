import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from geonesclick.config import load_config
from geonesclick.server import create_app
from geonesclick.settings import SettingsError, current, save

ORIGIN = {"Origin": "http://localhost:1420"}


def test_save_merges_into_existing_user_file(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('[vision]\nmodel = "a/b"\n\n[capture]\ncrop = [0.0, 0.1, 1.0, 1.0]\n')
    cfg = save({"coach": {"help_level": 2}}, user)
    assert cfg.coach.help_level == 2
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
    user.write_text('[coach]\nhelp_level = 1\n')
    with pytest.raises(SettingsError, match="help_level"):
        save({"coach": {"help_level": 7}}, user)
    assert tomllib.loads(user.read_text())["coach"]["help_level"] == 1


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
    res = http.post("/settings", json={"coach": {"help_level": 3}, "metas": {"max_categories": 2}},
                    headers=ORIGIN)
    assert res.status_code == 200
    assert engine.cfg.coach.help_level == 3 and engine.cfg.metas.max_categories == 2
    assert tomllib.loads(user.read_text())["coach"]["help_level"] == 3


def test_settings_route_rejects_base_url(client):
    http, engine, _ = client
    res = http.post("/settings", json={"vision": {"base_url": "https://attaquant.example"}}, headers=ORIGIN)
    assert res.status_code == 422
    assert engine.cfg.vision.base_url.startswith("https://integrate.api.nvidia.com")


def test_foreign_origin_cannot_change_settings(client):
    http, *_ = client
    res = http.post("/settings", json={"coach": {"help_level": 2}}, headers={"Origin": "https://x.example"})
    assert res.status_code == 403


@pytest.mark.parametrize("model", ["../../etc", "a b/c", "x" * 200, "sans-slash"])
def test_model_test_rejects_malformed_ids(client, model):
    http, *_ = client
    assert http.post("/models/test", json={"model": model}, headers=ORIGIN).status_code == 422


def test_save_keeps_comments_and_layout(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('# mon commentaire\n[coach]\nhelp_level = 1  # je préfère chercher\n')
    save({"coach": {"help_level": 2}}, user)
    text = user.read_text()
    assert text.startswith("# mon commentaire\n")
    assert "help_level = 2  # je préfère chercher" in text


def test_save_only_writes_values_that_change(tmp_path):
    user = tmp_path / "config.toml"
    defaults = current(load_config(tmp_path / "absent.toml"))
    save(defaults | {"coach": {"help_level": 2, "language": "fr"}}, user)
    written = tomllib.loads(user.read_text())
    assert written == {"coach": {"help_level": 2}}  # le reste suit toujours les valeurs par défaut


def test_unreadable_user_file_is_refused_without_writing(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("coach = 3\n")
    with pytest.raises(SettingsError):
        save({"coach": {"help_level": 2}}, user)
    assert user.read_text() == "coach = 3\n"


def test_every_setting_is_editable_or_file_only():
    """Tout est configurable : chaque clé de la configuration est modifiable à l'écran, ou réservée au
    fichier pour une raison de sécurité écrite. Une clé ajoutée sans être rangée fait échouer ce test."""
    from geonesclick.settings import EDITABLE, FILE_ONLY

    cfg = load_config(Path("/nonexistent.toml"))
    for section in type(cfg).model_fields:
        keys = set(type(getattr(cfg, section)).model_fields)
        editable, reserved = set(EDITABLE.get(section, ())), set(FILE_ONLY.get(section, {}))
        assert not editable & reserved, section
        assert keys == editable | reserved, f"{section} : non rangées {sorted(keys - editable - reserved)}"


def test_file_only_values_come_with_a_reason(client):
    http, *_ = client
    data = http.get("/settings/file-only", headers=ORIGIN).json()
    assert data["vision"]["base_url"]["value"].startswith("https://")
    assert all(entry["why"] for keys in data.values() for entry in keys.values())


def test_streetclip_labels_are_recomputed_live(client):
    http, engine, _ = client

    class Clip:
        device, cfg, relabelled = "cpu", None, 0

        def set_labels(self, cfg):
            self.cfg, self.relabelled = cfg, self.relabelled + 1

    engine.streetclip = Clip()
    ok = http.post("/settings", json={"streetclip": {"prompt": "A photo taken in {}."}}, headers=ORIGIN)
    assert ok.status_code == 200 and engine.streetclip.relabelled == 1
    http.post("/settings", json={"streetclip": {"top_k": 7}}, headers=ORIGIN)
    assert engine.streetclip.relabelled == 1 and engine.streetclip.cfg.top_k == 7  # rien à recalculer


def test_excluded_country_can_be_restored(client):
    http, engine, _ = client
    http.post("/settings", json={"streetclip": {"exclude_countries": ["RU"]}}, headers=ORIGIN)
    assert "RU" not in engine.cfg.streetclip.countries.values()
    listed = http.get("/settings", headers=ORIGIN).json()["streetclip"]["countries"]
    assert "RU" in listed.values()  # toujours proposé à l'écran, pour pouvoir le remettre


@pytest.mark.parametrize(
    "changes",
    [
        {"streetclip": {"prompt": "sans accolades"}},
        {"streetclip": {"prompt": "A photo in {}.{:>999999999}"}},  # largeur géante via str.format
        {"streetclip": {"prompt": "A photo in {}{0.__class__}"}},
        {"streetclip": {"device": "cuda; rm -rf /"}},
        {"streetclip": {"countries": {"Atlantis": "atl"}}},
        {"streetclip": {"exclude_countries": ["AL", "AD", "AR", "AU", "AT", "BD", "BE", "BT", "BO", "BW", "BR", "BG",
                                              "KH", "CA", "CL", "CO", "HR", "CZ", "DK", "DO", "EC", "EE", "SZ", "FI",
                                              "FR", "DE", "GH", "GR", "GT", "HU", "IS", "IN", "ID", "IE", "IL", "IT",
                                              "JP", "JO", "KE", "KG", "LV", "LS", "LT", "LU", "MY", "MT", "MX", "MN",
                                              "ME", "NL", "NZ", "NG", "MK", "NO", "PA", "PE", "PH", "PL", "PT", "RO",
                                              "RU", "RW", "SN", "RS", "SG", "SK", "SI", "ZA", "KR", "ES", "LK", "SE",
                                              "CH", "TW", "TH", "TN", "TR", "UG", "UA", "AE", "GB", "US", "UY"]}},
    ],
)
def test_invalid_analysis_settings_are_refused(tmp_path, changes):
    with pytest.raises(SettingsError):
        save(changes, tmp_path / "config.toml")


def test_restart_settings_are_reported(client):
    http, *_ = client
    res = http.post("/settings", json={"streetclip": {"device": "cpu"}}, headers=ORIGIN).json()
    assert res["restart"] == ["streetclip.device"]
