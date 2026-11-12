"""Coach's map: borders (country of a point), PLONK cloud (reduced network, no real weights), server, settings."""

import asyncio

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from geonesclick.borders import Borders
from geonesclick.config import Config, load_config
from geonesclick.plonk import Cloud, GeoAdaLNMLP, PlonkCloud, summarise, zones
from geonesclick.server import create_app
from geonesclick.settings import SettingsError, save
from geonesclick.streetclip import CountryScore

ORIGIN = {"Origin": "http://localhost:1420"}
COND = 16  # small simulated [CLS] vector (1024 with StreetCLIP)


@pytest.fixture(scope="module")
def borders():
    return Borders()


@pytest.fixture
def cfg(tmp_path):
    user = tmp_path / "config.toml"
    user.write_text("[capture]\nnotify = false\nsave_to_disk = false\n\n[plonk]\npoints = 64\nsteps = 10\n")
    return load_config(user)


def tiny_cloud(cfg) -> PlonkCloud:
    torch.manual_seed(0)
    return PlonkCloud(cfg.plonk, "cpu", net=GeoAdaLNMLP(input_dim=3, dim=32, depth=2, expansion=2, cond_dim=COND))


# --- Borders ------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("lat", "lon", "code"),
    [
        (48.86, 2.35, "FR"),  # Paris (ISO_A2 is -99 for France: ISO_A2_EH fixes it)
        (59.91, 10.75, "NO"),  # Oslo (same case)
        (-29.31, 27.48, "LS"),  # Maseru: enclave inside South Africa, which must not win
        (-26.20, 28.05, "ZA"),  # Johannesburg
        (40.0, -30.0, ""),  # Atlantic
    ],
)
def test_country_of_a_point(borders, lat, lon, code):
    assert borders.countries_of(np.array([lat]), np.array([lon])) == [code]


def test_outlines_keep_only_the_code(borders):
    features = borders.geojson["features"]
    assert len(features) > 200
    assert all(set(f["properties"]) == {"code"} and len(f["properties"]["code"]) == 2 for f in features)


# --- Cloud --------------------------------------------------------------------------------------------
def test_sample_is_on_the_sphere_and_reproducible(cfg):
    plonk = tiny_cloud(cfg)
    cls = torch.randn(1, COND)
    a, b = plonk.sample(cls), plonk.sample(cls)
    assert a.lat.shape == (64,) and np.all(np.abs(a.lat) <= 90) and np.all(np.abs(a.lon) <= 180)
    np.testing.assert_array_equal(a.lat, b.lat)  # same view, same seed: same cloud
    assert not np.array_equal(a.lat, plonk.sample(cls, seed=1).lat)


def blob(lat0, lon0, n, km=40, seed=0):
    """n points around (lat0, lon0), a few tens of km away."""
    rng = np.random.default_rng(seed)
    return lat0 + rng.normal(0, km / 111, n), lon0 + rng.normal(0, km / 111 / np.cos(np.radians(lat0)), n)


def test_two_separate_clusters_make_two_zones():
    (a_lat, a_lon), (b_lat, b_lon) = blob(45.5, 9.2, 60), blob(41.9, 12.5, 40, seed=1)  # Milan, Rome
    found = zones(np.r_[a_lat, b_lat], np.r_[a_lon, b_lon], share=0.8, link_km=150, min_part=0.05)
    assert len(found) == 2
    assert found[0]["part"] > found[1]["part"]  # the biggest first
    north = np.array(found[0]["polygon"])
    assert 44 < north[:, 0].mean() < 47 and 8 < north[:, 1].mean() < 11  # around Milan
    assert 50 < found[0]["width_km"] < 400


def test_small_groups_and_isolated_points_are_left_out():
    lat, lon = blob(60.0, 7.0, 95)
    lat, lon = np.r_[lat, -33.9, 35.7], np.r_[lon, 151.2, 139.7]  # two isolated points (Sydney, Tokyo)
    found = zones(lat, lon, share=0.8, link_km=150, min_part=0.05)
    assert len(found) == 1 and found[0]["part"] == pytest.approx(0.8, abs=0.01)


def test_zone_across_the_antimeridian_stays_small():
    lat, lon = blob(-17.8, 179.9, 50, km=30)  # Fiji, on both sides of 180°
    lon = (lon + 180) % 360 - 180
    found = zones(lat, lon, share=0.8, link_km=150, min_part=0.05)
    assert len(found) == 1 and found[0]["width_km"] < 300


def test_summary_gives_zones_by_country(cfg, borders):
    lat, lon = blob(45.5, 9.2, 64)  # Lombardy
    out = summarise(Cloud(lat, lon, 1.0), borders.countries_of(lat, lon), cfg.plonk)
    assert set(out) == {"zones", "zones_by_country", "ms"}
    assert "IT" in out["zones_by_country"]
    assert out["zones"][0]["countries"][0][0] == "IT"  # main country of the zone
    assert all(round(v, 3) == v for z in out["zones"] for p in z["polygon"] for v in p)


# --- Server -------------------------------------------------------------------------------------------
class FakeClip:
    device = "cpu"

    def analyse(self, _img):
        scores = [CountryScore("Norway", "NO", 0.6), CountryScore("Sweden", "SE", 0.4)]
        return scores, 5.0, None, torch.randn(1, COND)


def run_analyse(engine) -> list[dict]:
    engine.capture.grab = lambda: Image.new("RGB", (64, 40))
    engine.streetclip = FakeClip()
    engine.cfg.vision.enabled = False
    sent = []

    async def broadcast(message):
        sent.append(message)

    engine.broadcast = broadcast

    async def run():
        assert (await engine.analyse())["ok"]
        await asyncio.gather(*engine.background)

    asyncio.run(run())
    return sent


def test_analysis_sends_a_cloud_after_streetclip(cfg, borders):
    engine = create_app(cfg).state.engine
    engine.plonk, engine.borders = tiny_cloud(cfg), borders
    sent = run_analyse(engine)
    types = [m["type"] for m in sent]
    assert types.index("streetclip") < types.index("cloud")  # the cloud never delays the help
    clip = next(m for m in sent if m["type"] == "streetclip")
    cloud = next(m for m in sent if m["type"] == "cloud")
    assert clip["cloud"] is True and cloud["id"] == clip["id"] and "zones" in cloud and "points" not in cloud


def test_no_cloud_when_plonk_is_off(cfg):
    engine = create_app(cfg).state.engine
    sent = run_analyse(engine)
    assert "cloud" not in [m["type"] for m in sent]
    assert next(m for m in sent if m["type"] == "streetclip")["cloud"] is False


def test_cloud_failure_is_reported_without_breaking_the_analysis(cfg, borders):
    engine = create_app(cfg).state.engine
    engine.plonk, engine.borders = tiny_cloud(cfg), borders

    def broken(*_args, **_kwargs):
        raise RuntimeError("CUDA out of memory")

    engine.plonk.sample = broken
    cloud = next(m for m in run_analyse(engine) if m["type"] == "cloud")
    assert "error" in cloud and "zones" not in cloud


def test_country_outlines_endpoint(cfg):
    client = TestClient(create_app(cfg), base_url="http://127.0.0.1:47615")
    res = client.get("/map/countries", headers=ORIGIN)
    assert res.status_code == 200 and res.json()["type"] == "FeatureCollection"
    assert client.get("/map/countries", headers={"Origin": "https://site-malveillant.example"}).status_code == 403


def test_state_exposes_map_settings(cfg):
    state = create_app(cfg).state.engine.state()
    assert state["map"]["tile_url"].startswith("https://tile.openstreetmap.org/")
    assert state["plonk"] == {"enabled": True, "ready": False, "message": "waiting for StreetCLIP"}


def test_turning_plonk_off_frees_it(cfg, tmp_path):
    app = create_app(cfg, tmp_path / "config.toml")
    engine = app.state.engine
    engine.plonk = tiny_cloud(cfg)
    client = TestClient(app, base_url="http://127.0.0.1:47615")
    assert client.post("/settings", json={"plonk": {"enabled": False}}, headers=ORIGIN).status_code == 200
    assert engine.plonk is None and engine.state()["plonk"]["message"] == "off"


# --- Configuration ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "changes",
    [
        {"map": {"tile_url": "https://attaquant.example/{z}/{x}/{y}.png"}},  # server: file only
        {"map": {"attribution_url": "https://attaquant.example/"}},
        {"plonk": {"model": "someone/else"}},
        {"plonk": {"revision": "0" * 40}},
    ],
)
def test_tile_server_links_and_models_are_file_only(tmp_path, changes):
    with pytest.raises(SettingsError):
        save(changes, tmp_path / "config.toml")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("tile_url", "http://tile.openstreetmap.org/{z}/{x}/{y}.png"),  # HTTP refused
        ("tile_url", "https://tile.example/sans-zoom.png"),
        ("tile_url", 'https://x.example/{z}/"><script>'),
        ("tile_filter", "url(https://x.example/a.svg#f)"),  # no URL in the CSS filter
        ("tile_filter", "invert(1); background: red"),
        ("max_zoom", 20),
    ],
)
def test_invalid_map_values_are_refused(key, value):
    data = load_config().model_dump()
    data["map"][key] = value
    with pytest.raises(ValidationError):
        Config.model_validate(data)


def test_plonk_steps_and_points_are_bounded():
    data = load_config().model_dump()
    data["plonk"]["steps"] = 5
    with pytest.raises(ValidationError):
        Config.model_validate(data)
