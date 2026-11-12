# Compatibility

## What GeoNesClick needs

- **64-bit Linux (x86_64) with glibc 2.39 or later**: the AppImage is built on Ubuntu 24.04, so it runs on the
  systems at least as recent (Ubuntu 24.04+, Debian 13, Fedora 40+, Arch…).
- **GNOME** (Wayland or Xorg): the screen is captured through GNOME's sharing portal and the shortcuts are GNOME
  settings. Other desktops (KDE, Xfce, Cinnamon…) are not supported for now.
- **System components that come with GNOME** (GStreamer, its PipeWire source, GObject Introspection, Cairo): the
  installer checks them and installs a missing one with one click, after your password, through apt (Debian,
  Ubuntu), dnf (Fedora), pacman (Arch) or zypper (openSUSE), with each distribution's package names; the command is
  shown too. Only apt has been tried for real. With another package manager, Debian's names are shown as a hint.

## Reported systems

Each release also installs the engine on Ubuntu 24.04 and 26.04, Debian 13, Fedora 45, Arch and openSUSE Tumbleweed
(fresh containers, without a desktop: the system components under the installer's names, the engine, a StreetCLIP
analysis). The whole app, desktop included, is only tested by the maintainer on Ubuntu. Every other line comes from a
[system report](https://github.com/MrNesClick/GeoNesClick/issues/new?template=system-report.yml): please send yours,
even when everything works.

| System | Desktop | Session | Graphics | Version | Result | Source |
|---|---|---|---|---|---|---|
| Ubuntu 24.04.5 | GNOME 46 | Wayland | NVIDIA | 0.1.0 | Works | maintainer's machine |
| Ubuntu 26.04.1 (fresh install) | GNOME 50 | Wayland | none | 0.1.1 | Works | maintainer, VM |
| Ubuntu 24.04.5 (fresh install) | GNOME 46 | Wayland | none | 0.2.3 | Works; `libgirepository-2.0-0` installed with one click | maintainer, VM |

A line is added for each report, with a link to it; a failure stays listed until a version fixes it. A report where
everything works also adds the system (distribution and version) to the "Validated on" list of both READMEs.
