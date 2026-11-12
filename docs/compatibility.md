# Compatibility

## What GeoNesClick needs

- **64-bit Linux (x86_64) with glibc 2.39 or later**: the AppImage is built on Ubuntu 24.04, so it runs on the
  systems at least as recent (Ubuntu 24.04+, Debian 13, Fedora 40+, Arch…).
- **GNOME** (Wayland or Xorg): the screen is captured through GNOME's sharing portal and the shortcuts are GNOME
  settings. Other desktops (KDE, Xfce, Cinnamon…) are not supported for now.
- **System components that come with GNOME** (GStreamer, its PipeWire source, GObject Introspection, Cairo): the
  installer checks them. On Debian, Ubuntu and their derivatives (apt), it installs a missing one with one click;
  elsewhere it shows the Debian package name, to look up in your package manager.

## Reported systems

Only Ubuntu is tested by the maintainer. Every other line comes from a
[system report](https://github.com/MrNesClick/GeoNesClick/issues/new?template=system-report.yml): please send yours,
even when everything works.

| System | Desktop | Session | Graphics | Version | Result | Source |
|---|---|---|---|---|---|---|
| Ubuntu 24.04.5 | GNOME 46 | Wayland | NVIDIA | 0.1.0 | Works | maintainer's machine |
| Ubuntu 26.04.1 (fresh install) | GNOME 50 | Wayland | none | 0.1.1 | Works | maintainer, VM |
| Ubuntu 24.04.5 (fresh install) | GNOME 46 | Wayland | none | 0.2.1 | Engine installation fails (fixed in 0.2.2); `libgirepository-2.0-0` to install | maintainer, VM |

A line is added for each report, with a link to it; a failure stays listed until a version fixes it.
