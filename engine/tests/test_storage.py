"""Réglages › Stockage : tailles, limite des caches qui grossissent, « Vider » (fichiers connus seulement)."""

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
        os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))  # FR le plus ancien, BG le plus récent
    write(plonkit / "plonkit.sqlite", 700)
    write(plonkit / "raw" / "france.json", 50)
    write(captures / "capture-20261107-1.png", 200)
    write(captures / "mark-20261107-1-1.png", 20)
    for folder in (places, plonkit, captures):
        write(folder / "a-moi.txt", 10)  # fichier étranger au coach : jamais supprimé
    return places, plonkit, captures


def test_inventory_gives_each_size(folders):
    items = {i["id"]: i for i in storage.inventory(*folders)}
    assert items["villages"]["size"] == 900 and items["villages"]["detail"] == "BG, FR, IT"
    assert items["lieux"]["size"] == 1500 and items["plonkit"]["size"] == 750 and items["captures"]["size"] == 220
    assert items["plonkit"]["confirm"] and items["villages"]["kind"] == "cache"


def test_least_recently_used_villages_go_first(folders):
    places, _, _ = folders
    assert storage.evict(places, 650, keep={"FR"}) == ["IT"]  # FR gardé (manche en cours), IT le plus ancien ensuite
    assert sorted(f.name for f in storage.village_files(places)) == ["detail-BG-v4.sqlite", "detail-FR-v4.sqlite"]
    assert (places / "places-v4.sqlite").exists()  # le socle ne part jamais tout seul


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
    assert {i["id"] for i in c.get("/storage").json()["items"]} == {"villages", "lieux", "plonkit", "captures"}
    res = c.post("/storage/clear", json={"id": "captures"}, headers=ORIGIN).json()
    assert res["freed"] == 220 and not storage.capture_files(captures)
    c.post("/storage/clear", json={"id": "lieux"}, headers=ORIGIN)
    assert not storage.base_place_files(places) and not storage.village_files(places)
    assert engine.places is None and "prochain démarrage" in engine.places_message


def test_clearing_is_refused_from_a_foreign_origin_or_for_unknown_items(client):
    c, _ = client
    assert c.post("/storage/clear", json={"id": "captures"}, headers={"Origin": "https://x.example"}).status_code == 403
    assert c.post("/storage/clear", json={"id": "dataset"}, headers=ORIGIN).status_code == 422  # jamais tes données


def test_lowering_the_limit_evicts_now(client, folders):
    import asyncio

    c, engine = client
    places, _, _ = folders
    asyncio.run(engine.apply_settings({"storage": {"max_cache_mb": 50}}))  # 900 octets < 50 Mo : rien ne part
    assert len(storage.village_files(places)) == 3
