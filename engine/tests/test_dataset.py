import pytest
from PIL import Image

from geonesclick.capture import prune_captures
from geonesclick.dataset import Dataset, DatasetError, progress


@pytest.fixture
def frame():
    return Image.new("RGB", (64, 40), (10, 20, 30))


def test_add_saves_raw_image_and_label(tmp_path, frame):
    ds = Dataset(tmp_path)
    label = ds.add("20261107-080023-137", frame, "LV", found=True, predicted="EE", area='côte "ouest"')
    assert (tmp_path / "images" / label.file).exists()
    [read] = ds.labels()
    assert (read.country, read.found, read.predicted, read.layout) == ("LV", True, "EE", "fenêtre 64x40")
    assert read.area == 'côte "ouest"'  # guillemets correctement échappés en TOML


def test_found_false_is_kept(tmp_path, frame):
    ds = Dataset(tmp_path)
    ds.add("20261107-080023-137", frame, "RS", found=False)
    assert ds.labels()[0].found is False


def test_relabel_replaces_previous_entry(tmp_path, frame):
    ds = Dataset(tmp_path)
    ds.add("20261107-080023-137", frame, "HR")
    ds.add("20261107-080023-137", frame, "RS")
    assert [lb.country for lb in ds.labels()] == ["RS"]


@pytest.mark.parametrize("bad", ["../../etc/passwd", "20261107-080023-137/../x", "abc", "", "20261107-080023-1370"])
def test_invalid_capture_id_is_rejected(tmp_path, frame, bad):
    with pytest.raises(DatasetError):
        Dataset(tmp_path).add(bad, frame, "SE")
    assert not (tmp_path / "images").exists() or not any((tmp_path / "images").iterdir())


def test_existing_labels_without_new_fields_still_load(tmp_path):
    (tmp_path / "labels.toml").write_text('[[capture]]\nfile = "a.png"\ncountry = "NO"\n')
    [lb] = Dataset(tmp_path).labels()
    assert lb.found is None and lb.predicted == ""


def test_progress(tmp_path, frame):
    ds = Dataset(tmp_path)
    ds.add("20261107-080000-001", frame, "RS", found=False, predicted="HR")
    ds.add("20261107-080000-002", frame, "RS", found=True, predicted="RS")
    ds.add("20261107-080000-003", frame, "NO", found=True, predicted="NO")
    ds.add("20261107-080000-004", frame, "SE")  # non renseigné : ignoré pour le joueur
    p = progress(ds.labels())
    assert (p.rounds, p.found) == (3, 2)
    assert p.by_country == {"RS": (2, 1), "NO": (1, 1)}
    assert (p.model_top1, p.model_rounds) == (2, 3)


def test_prune_keeps_most_recent(tmp_path):
    for i in range(5):
        (tmp_path / f"capture-20261107-08000{i}-000.png").write_bytes(b"x")
    (tmp_path / "autre.png").write_bytes(b"x")
    assert prune_captures(tmp_path, 2) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "autre.png", "capture-20261107-080003-000.png", "capture-20261107-080004-000.png"]


def test_guessed_country_decides_found_and_feeds_confusions(tmp_path, frame):
    ds = Dataset(tmp_path)
    ds.add("20261107-080000-001", frame, "RS", guessed="HR", found=True)  # « found » se déduit de la réponse
    ds.add("20261107-080000-002", frame, "RS", guessed="HR")
    ds.add("20261107-080000-003", frame, "SE", guessed="NO")
    ds.add("20261107-080000-004", frame, "NO", guessed="NO")
    labels = ds.labels()
    assert [lb.found for lb in labels] == [False, False, False, True]
    p = progress(labels)
    assert [(c.country, c.guessed, c.count) for c in p.confusions] == [("RS", "HR", 2), ("SE", "NO", 1)]
