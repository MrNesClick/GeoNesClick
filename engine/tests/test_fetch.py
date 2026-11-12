import errno

import huggingface_hub
import pytest
from huggingface_hub.errors import LocalEntryNotFoundError

from geonesclick import fetch


def _failing(exc):
    def download(*_args, **_kwargs):
        raise exc
    return download


@pytest.mark.parametrize("exc, expected", [
    (LocalEntryNotFoundError("An error happened while trying to locate the file on the Hub and we cannot find\n"
                             "the requested files in the local cache. Please check your connection."),
     "LocalEntryNotFoundError: An error happened while trying to locate the file on the Hub and we cannot find "
     "the requested files in the local cache."),
    (OSError(errno.ENOSPC, "No space left on device"), "No space left on device"),
])
def test_a_failed_download_is_one_readable_line_naming_the_hub(monkeypatch, capsys, exc, expected):
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", _failing(exc))
    assert fetch.main(["plonk"]) == 1
    err = capsys.readouterr().err.strip()
    assert "\n" not in err and "Traceback" not in err
    assert err.startswith("erreur : nicolas-dufour/PLONK_OSV_5M/config.json non téléchargé depuis https://huggingface.co/ : ")
    assert expected in err


def test_files_are_announced_one_by_one(monkeypatch, capsys):
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda *a, **k: "/cache/file")
    assert fetch.main(["plonk"]) == 0
    assert capsys.readouterr().out.splitlines() == ["FICHIER nicolas-dufour/PLONK_OSV_5M/config.json",
                                                     "FICHIER nicolas-dufour/PLONK_OSV_5M/model.safetensors"]


def test_unknown_model_is_refused(capsys):
    assert fetch.main(["other"]) == 2
    assert "usage" in capsys.readouterr().err
