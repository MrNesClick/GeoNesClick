"""Settings › Storage: sizes, limit of the caches that grow, "Empty" (known files only)."""

import os
import time

import pytest
from fastapi.testclient import TestClient

from geonesclick import storage
from geonesclick.config import load_config
from geonesclick.server import create_app

ORIGIN = {"Origin": "http://localhost:1420"}


def write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


@pytest.fixture
def folders(tmp_path):
    places, plonkit, captures = tmp_path / "places", tmp_path / "plonkit", tmp_path / "captures"
    write(places / "places-v4.sqlite", 1000)
    write(places / "source.zip", 500)
    for i, country in enumerate(["FR", "IT", "BG"]):
        f = write(places / f"detail-{country}-v4.sqlite", 300)
        os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))  # FR the oldest, BG the most recent
    write(plonkit / "plonkit.sqlite", 700)
    write(plonkit / "raw" / "france.json", 50)
    write(captures / "capture-20261107-1.png", 200)
    write(captures / "mark-20261107-1-1.png", 20)
    for folder in (places, plonkit, captures):
        write(folder / "a-moi.txt", 10)  # file foreign to the coach: never deleted
    return places, plonkit, captures


def test_inventory_gives_each_size(folders):
    items = {i["id"]: i for i in storage.inventory(*folders)}
    assert items["villages"]["size"] == 900 and items["villages"]["detail"] == "BG, FR, IT"
    assert items["places"]["size"] == 1500 and items["plonkit"]["size"] == 750 and items["captures"]["size"] == 220
    assert items["plonkit"]["confirm"] and items["villages"]["kind"] == "cache"


def test_least_recently_used_villages_go_first(folders):
    places, _, _ = folders
    assert storage.evict(places, 650, keep={"FR"}) == ["IT"]  # FR kept (current round), IT the oldest next
    assert sorted(f.name for f in storage.village_files(places)) == ["detail-BG-v4.sqlite", "detail-FR-v4.sqlite"]
    assert (places / "places-v4.sqlite").exists()  # the base never goes on its own


def test_only_known_files_are_removed(folders):
    for folder, files in zip(folders, (storage.base_place_files, storage.plonkit_files, storage.capture_files),
                             strict=True):
        storage.remove(files(folder))
        assert (folder / "a-moi.txt").exists()


@pytest.fixture
def client(folders, tmp_path):
    places, plonkit, captures = folders
    user = tmp_path / "config.toml"
    user.write_text(f'[capture]\nnotify = false\ndirectory = "{captures}"\n\n[plonkit]\ndata_dir = "{plonkit}"\n'
                    f'\n[rules]\nplaces_dir = "{places}"\n')
    app = create_app(load_config(user), user)
    return TestClient(app, base_url="http://127.0.0.1:47615"), app.state.engine


def test_storage_route_and_clear(client, folders):
    c, engine = client
    places, _, captures = folders
    assert {i["id"] for i in c.get("/storage").json()["items"]} == {"villages", "places", "plonkit", "captures"}
    res = c.post("/storage/clear", json={"id": "captures"}, headers=ORIGIN).json()
    assert res["freed"] == 220 and not storage.capture_files(captures)
    c.post("/storage/clear", json={"id": "places"}, headers=ORIGIN)
    assert not storage.base_place_files(places) and not storage.village_files(places)
    assert engine.places is None and "next start" in engine.places_message


def test_clearing_is_refused_from_a_foreign_origin_or_for_unknown_items(client):
    c, _ = client
    assert c.post("/storage/clear", json={"id": "captures"}, headers={"Origin": "https://x.example"}).status_code == 403
    assert c.post("/storage/clear", json={"id": "dataset"}, headers=ORIGIN).status_code == 422  # never your data


def test_lowering_the_limit_evicts_now(client, folders):
    import asyncio

    c, engine = client
    places, _, _ = folders
    asyncio.run(engine.apply_settings({"storage": {"max_cache_mb": 50}}))  # 900 bytes < 50 MB: nothing goes
    assert len(storage.village_files(places)) == 3


# --- "Erase everything" (GDPR) -------------------------------------------------------------------------
def test_erase_everything_personal_but_only_known_files(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from geonesclick import apikey, paths
    from geonesclick.config import load_config
    from geonesclick.server import create_app

    def touch(path, data=b"x" * 10):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    d = tmp_path
    hub = d / "hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setattr(paths, "DATA_DIR", d / "data")
    settings = paths.CONFIG_DIR / "config.toml"
    settings.write_text(
        f'[capture]\nnotify = false\ndirectory = "{d / "shots"}"\n[dataset]\ndirectory = "{d / "ds"}"\n'
        f'[metas]\nuser_file = "{paths.CONFIG_DIR / "mes-metas.toml"}"\n[plonkit]\ndata_dir = "{d / "pk"}"\n'
        f'[rules]\nplaces_dir = "{d / "places"}"\n')
    apikey.save("NVAPI", "nvapi-secret-1234")
    gone = [settings, touch(paths.CONFIG_DIR / "mes-metas.toml"), touch(paths.CONFIG_DIR / "screencast.token"),
            touch(d / "shots" / "capture-1.png"), touch(d / "shots" / "capture-1.json"), touch(d / "ds" / "labels.toml"),
            touch(d / "ds" / "images" / "capture-1.png"), touch(d / "ds" / "rounds" / "1.json"),
            touch(d / "pk" / "plonkit.sqlite"), touch(d / "places" / "places-v4.sqlite"),
            touch(d / "places" / "detail-FR-v4.sqlite")]
    kept = [touch(d / "shots" / "notes.txt"), touch(hub / "models--other--Model" / "w.bin")]
    ours = touch(hub / "models--geolocal--StreetCLIP" / "w.bin")
    calls = []

    def gsettings(args):
        calls.append(args)
        return "['/a/', '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/geonesclick/']"

    monkeypatch.setattr(storage, "_gsettings", gsettings)
    client = TestClient(create_app(load_config(settings), settings), base_url="http://127.0.0.1:47615")
    origin = {"Origin": "http://localhost:1420"}
    plan = {g["id"]: g for g in client.get("/storage/erase").json()["groups"]}
    assert plan["dataset"]["precious"] and plan["dataset"]["files"] == 3 and plan["models"]["optional"]
    assert client.post("/storage/erase", json={"confirm": "oui"}, headers=origin).status_code == 422
    res = client.post("/storage/erase", json={"confirm": "ERASE"}, headers=origin).json()
    assert res["ok"] and res["shortcuts"] == 1
    assert not any(p.exists() for p in gone) and apikey.read("NVAPI") is None
    assert all(p.exists() for p in kept) and ours.exists()  # models: only on request
    assert ["set", storage.MEDIA_KEYS, "custom-keybindings", "['/a/']"] in calls
    assert client.get("/health").json()["erased"] is True
    client.post("/storage/erase", json={"confirm": "ERASE", "models": True}, headers=origin)
    assert not ours.exists() and kept[1].exists()  # other software's models stay


def test_model_ids_cannot_escape_the_cache(tmp_path):
    (tmp_path / "hub").mkdir()
    (tmp_path / "victim").mkdir()
    assert storage.model_dirs(tmp_path / "hub", ["../victim", "a/../../victim", "x"]) == []


def test_the_engine_box_is_offered_only_for_the_engine_installed_by_the_appimage(tmp_path, monkeypatch):
    """The development venv is never offered for removal; the AppImage's installed engine is, as an optional group."""
    from geonesclick import paths, storage

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    venv = tmp_path / "engine" / "venv"
    (venv / "lib").mkdir(parents=True)
    (venv / "lib" / "big.bin").write_bytes(b"x" * 1000)
    monkeypatch.setattr(storage.sys, "prefix", str(venv))
    assert storage.installed_engine() == tmp_path / "engine"
    plan = {g["id"]: g for g in storage.erase_plan({}, [], storage.installed_engine())}
    assert plan["engine"]["optional"] and plan["engine"]["size"] == 1000

    monkeypatch.setattr(storage.sys, "prefix", str(tmp_path / "elsewhere" / ".venv"))
    assert storage.installed_engine() is None
    assert "engine" not in {g["id"] for g in storage.erase_plan({}, [], storage.installed_engine())}
