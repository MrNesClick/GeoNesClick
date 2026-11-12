"""API key outside the repository: file readable by you only, never sent back in full, old .env migrated."""

import stat

import pytest
from fastapi.testclient import TestClient

from geonesclick import apikey, paths
from geonesclick.config import load_config
from geonesclick.server import create_app

ORIGIN = {"Origin": "http://localhost:1420"}


def test_key_is_saved_private_and_only_its_end_is_shown(monkeypatch):
    apikey.save("NVAPI", "  nvapi-abcdef123456  ")
    path = paths.CONFIG_DIR / "nvapi.key"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert apikey.read("NVAPI") == "nvapi-abcdef123456"
    assert apikey.hint("NVAPI") == {"source": "file", "end": "3456"}
    monkeypatch.setenv("NVAPI", "nvapi-from-env-9999")
    assert apikey.hint("NVAPI") == {"source": "env", "end": "9999"}  # takes priority
    apikey.forget("NVAPI")
    monkeypatch.delenv("NVAPI")
    assert apikey.read("NVAPI") is None


@pytest.mark.parametrize("bad", ["short", "with space 123", "a" * 301, "line\nbreak", "abcdefgh12345678"])
def test_invalid_keys_are_refused(bad):
    with pytest.raises(apikey.ApiKeyError):
        apikey.save("NVAPI", bad)


def test_name_cannot_escape_the_folder():
    with pytest.raises(apikey.ApiKeyError):
        apikey.key_file("../x")


def test_old_env_file_is_migrated_then_cleaned(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# NVIDIA API key\nNVAPI=nvapi-old-key-0001\nOTHER=kept\n")
    assert apikey.migrate_env("NVAPI", env) is True
    assert apikey.read("NVAPI") == "nvapi-old-key-0001"
    assert env.read_text() == "# NVIDIA API key\nOTHER=kept\n"  # the rest of the .env is kept
    assert apikey.migrate_env("NVAPI", env) is False  # only once


def test_settings_route_saves_without_ever_returning_the_key(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text(f'[capture]\nnotify = false\n\n[metas]\nuser_file = "{tmp_path / "m.toml"}"\n')
    client = TestClient(create_app(load_config(user), user), base_url="http://127.0.0.1:47615")
    res = client.post("/settings/api-key", json={"key": "nvapi-secret-7777"}, headers=ORIGIN)
    assert res.json() == {"ok": True, "key": {"source": "file", "end": "7777"}}
    assert "nvapi-secret" not in client.get("/health").text
    assert client.post("/settings/api-key", json={"key": "x y"}, headers=ORIGIN).status_code == 422
    assert client.post("/settings/api-key", json={"key": "nvapi-secret-7777"},
                       headers={"Origin": "https://x.example"}).status_code == 403
    assert client.post("/settings/api-key", json={"key": ""}, headers=ORIGIN).json()["key"] is None


def test_command_line_reads_the_key_from_stdin(monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("nvapi-from-stdin-4242\n"))
    assert apikey.main() == 0 and apikey.read("NVAPI") == "nvapi-from-stdin-4242"
    monkeypatch.setattr("sys.stdin", io.StringIO("bad key\n"))
    assert apikey.main() == 1
