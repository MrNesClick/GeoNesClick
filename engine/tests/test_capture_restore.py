"""Resuming the remembered window at the app's start, without the portal: each fake stream says how it ends."""

import pytest

from geonesclick import capture
from geonesclick.capture import CaptureError, CaptureService
from geonesclick.i18n import t


@pytest.fixture
def token(tmp_path, monkeypatch):
    path = tmp_path / "screencast.token"
    monkeypatch.setattr(capture, "TOKEN_FILE", path)
    return path


def service_with(streams):
    """A service whose streams end one after the other as given: (images shown?, error message or None)."""
    states, opened = [], []
    service = CaptureService(on_state=lambda *state: states.append(state))
    ends = iter(streams)

    def stream():
        opened.append(capture.TOKEN_FILE.exists())
        service._got_frame, error = next(ends)
        return (error, True) if error else (None, False)

    service._stream = stream
    return service, states, opened


def test_a_remembered_window_that_is_gone_is_forgotten_and_the_picker_opens(token):
    token.write_text("old")
    service, states, opened = service_with([(False, "target not found"), (True, None)])
    assert service._share() == (None, False)
    assert opened == [True, False]  # the second stream asked GNOME without the token
    assert not token.exists()
    assert states == [(False, t("capture.window_gone"), False, True)]


def test_the_picker_opens_only_once(token):
    token.write_text("old")
    service, _states, opened = service_with([(False, "target not found"), (False, "target not found")])
    assert service._share() == ("target not found", True)
    assert opened == [True, False]


@pytest.mark.parametrize("remembered, first_image", [(True, True), (False, False)])
def test_a_stream_that_showed_images_or_was_picked_is_not_retried(token, remembered, first_image):
    if remembered:
        token.write_text("old")
    service, states, opened = service_with([(first_image, "stream died")])
    assert service._share() == ("stream died", True)
    assert opened == [remembered]
    assert token.exists() == remembered
    assert states == []


def test_the_sharing_counts_as_active_only_from_its_first_image(token):
    service, states, _opened = service_with([])

    class Sink:
        def emit(self, _signal):
            return "sample"

    assert not service.alive
    service._on_sample(Sink())
    service._on_sample(Sink())
    assert service.alive
    assert states == [(True, t("capture.active"), False, False)]  # announced once


def test_a_capture_while_the_sharing_starts_says_no_image_yet(token):
    service, _states, _opened = service_with([])

    class Starting:
        def is_alive(self):
            return True

    service._thread = Starting()
    with pytest.raises(CaptureError, match=t("capture.no_image")):
        service.grab()
    service._thread = None
    with pytest.raises(CaptureError, match=t("capture.inactive")):
        service.grab()
