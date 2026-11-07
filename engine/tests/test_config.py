import pytest
from pydantic import ValidationError

from geonesclick import config


def test_defaults_load_without_user_file(tmp_path):
    cfg = config.load_config(tmp_path / "absent.toml")
    assert cfg.server.host == "127.0.0.1"
    assert cfg.capture.source == "window"
    assert cfg.coach.help_level == 4
    assert cfg.streetclip.countries["Hungary"] == "HU"


def test_user_file_overrides_only_given_keys(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('[capture]\nsound = false\n\n[vision]\nmodel = "autre/modele"\n')
    cfg = config.load_config(user)
    assert cfg.capture.sound is False
    assert cfg.capture.notify is True  # clé voisine conservée
    assert cfg.vision.model == "autre/modele"
    assert cfg.vision.timeout_s == 90  # valeur par défaut conservée


@pytest.mark.parametrize(
    "crop",
    [[0.5, 0.0, 0.4, 1.0], [0.0, 0.0, 1.2, 1.0], [0.0, 0.0, 1.0], [0.0, 0.6, 1.0, 0.6]],
)
def test_invalid_crop_is_rejected(tmp_path, crop):
    user = tmp_path / "config.toml"
    user.write_text(f"[capture]\ncrop = {crop}\n")
    with pytest.raises(ValidationError, match="capture.crop"):
        config.load_config(user)


def test_invalid_mask_names_its_index(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("[capture]\nmasks = [[0.0, 0.0, 0.5, 0.5], [0.9, 0.0, 0.1, 1.0]]\n")
    with pytest.raises(ValidationError, match=r"capture.masks\[1\]"):
        config.load_config(user)


def test_unknown_capture_source_is_rejected(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('[capture]\nsource = "tout"\n')
    with pytest.raises(ValidationError):
        config.load_config(user)


def test_read_secret_prefers_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text("CLE=depuis-fichier\n")
    monkeypatch.setenv("CLE", "depuis-env")
    assert config.read_secret("CLE") == "depuis-env"


def test_read_secret_falls_back_to_dotenv(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("CLE", raising=False)
    (tmp_path / ".env").write_text('AUTRE=x\nCLE = "nvapi-123"\nVIDE=\n')
    assert config.read_secret("CLE") == "nvapi-123"
    assert config.read_secret("VIDE") is None
    assert config.read_secret("ABSENTE") is None


def test_countries_can_be_excluded(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text('[streetclip]\nexclude_countries = ["ru", "UA"]\n')
    codes = set(config.load_config(user).streetclip.countries.values())
    assert "RU" not in codes and "UA" not in codes and "SE" in codes


def test_old_folders_are_moved_once_never_deleted(tmp_path, monkeypatch):
    """Ancien nom (GeoNesClick) → GeoNesClick : tes données suivent, rien n'est effacé."""
    from geonesclick import paths

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    (tmp_path / "config" / "geonesclick").mkdir(parents=True)
    (tmp_path / "config" / "geonesclick" / "config.toml").write_text("[coach]\n")
    (tmp_path / "data" / "geonesclick" / "plonkit").mkdir(parents=True)
    (tmp_path / "data" / "geonesclick").mkdir()  # déjà là : on n'y touche pas
    moved = paths.migrate_legacy()
    assert (tmp_path / "config" / "geonesclick" / "config.toml").read_text() == "[coach]\n"
    assert len(moved) == 1 and (tmp_path / "data" / "geonesclick" / "plonkit").is_dir()
    assert paths.migrate_legacy() == []  # une seule fois
