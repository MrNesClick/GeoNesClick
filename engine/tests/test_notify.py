from gi.repository import Gio, GLib

from geonesclick.notify import Notifier


def _no_bus(*_args):
    raise GLib.Error("Cannot autolaunch D-Bus without X11 $DISPLAY")


def test_missing_session_bus_does_not_break_the_engine(monkeypatch, capsys):
    monkeypatch.setattr(Gio, "bus_get_sync", _no_bus)
    notifier = Notifier(enabled=True, sound=False)  # built at engine start: must not touch the bus
    notifier.send("Capture enregistrée")
    assert "pas de bus de session" in capsys.readouterr().out


def test_disabled_notifier_never_opens_the_bus(monkeypatch):
    def fail(*_args):
        raise AssertionError("bus opened while notifications are off")

    monkeypatch.setattr(Gio, "bus_get_sync", fail)
    Notifier(enabled=False, sound=False).send("Capture enregistrée")
