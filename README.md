**English** | [Français](README.fr.md)

# GeoNesClick

AI-assisted geolocation coach to train at GeoGuessr and at the basics of image geolocation (OSINT). Press a shortcut
during a round: the coach looks at the view on your screen and points you to the useful clues, with as much help as
you choose.

> **For practice only.** The coach only reads the image on your screen, never the game's data. GeoGuessr's
> [community rules](https://www.geoguessr.com/community-rules) count third-party tools that give an unfair advantage
> as cheating: never use it in multiplayer or competitive play, or wherever your score is compared with others.

## Features

- **Four help levels**, from "where to look" to a reasoned answer, with its proof when a text read gives one.
- **Local AI** (StreetCLIP) for the likely countries, in about 60 ms with an NVIDIA card (1.6 s on a 4-core
  processor), plus a remote vision model that reads the text in the view.
- **Marks**: draw a box around a sign or a shop front; the coach reads it and draws local, sourced conclusions.
- **Map** of the likely zones (PLONK, computed locally) and of the places read on your signs.
- **Progress tracking**: after each round, "Where was it?" records the real country and shows your confusions.
- Everything is configurable from the app, and everything it downloads is listed before the first byte.

The interface is in English and French (chosen on first launch, changeable in the Settings).

## Requirements

- 64-bit Linux with GNOME (Wayland or Xorg) and glibc 2.39 or later.
  - **Validated on**: Ubuntu 24.04, Ubuntu 26.04.
  - Other distributions with GNOME and glibc 2.39 or later (Debian 13, Fedora 40 or later…) are not validated yet
    but should work: [tell us how it went][report]; a report where everything works adds your system to this list
    ([details of each report](docs/compatibility.md)).
- About 11 GB of free disk space during the installation, 8 GB used afterwards (about 3 GB without an NVIDIA card)
- 8 GB of RAM (without an NVIDIA card, the engine alone uses about 2.5 GB)
- An NVIDIA card (recommended; without one, the local AI runs on the processor, more slowly)
- A free NVIDIA API key from [build.nvidia.com](https://build.nvidia.com) (recommended: it reads the text in the
  view and translates the tips)

## Install

1. Download `GeoNesClick_<version>_amd64.AppImage` from the
   [Releases](https://github.com/MrNesClick/GeoNesClick/releases) page.
2. Make it executable (right click › Properties › *Executable as Program*, or `chmod +x GeoNesClick_*.AppImage`),
   then open it.
3. On first launch, an assistant checks your system and installs a missing component with one click, after your
   password (apt, dnf, pacman or zypper). It then lists everything it will download, with the size and the licence
   of each item. Once you accept, it installs the engine in `~/.local/share/geonesclick/` and the AI models in
   `~/.cache/huggingface/`; nothing else goes into the system. The download goes through GitHub, PyPI, Hugging Face
   and, without an NVIDIA card, PyTorch: if one of them does not answer, the assistant names it. Retry later: what
   is already downloaded is kept.
4. Choose your options, enter your API key if you have one, and you are ready. One option, off by default, adds
   GeoNesClick to the applications menu, with its own icon in the dock; it can be changed in Settings › GNOME
   integration, like the keyboard shortcuts.
5. The assistant also copies the application itself to `~/.local/share/geonesclick/GeoNesClick.AppImage`, under a
   name without its version, and the applications menu launches it from there. Why: the menu entry and the updates
   need a file that stays put, whereas yours carries a version in its name and lives in your downloads. Renaming,
   moving or deleting the file you downloaded therefore breaks nothing; once the coach has started, it tells you
   that it can be deleted.

### Update

Download the new AppImage and open it once. The update runs on its own, without a question:

- your settings, your API key and your data are kept; the settings are migrated in the background when the new
  version needs it;
- only the libraries that changed are downloaded (a few MB when only GeoNesClick changed, instead of 3.1 GB with an
  NVIDIA card), so the engine's size must be free on the disk for a moment;
- while it runs, it shows what changed since your version (the [changelog](CHANGELOG.md) entries, in English);
- the new version then replaces the installed copy, the menu opens it from then on, and the coach tells you once that
  the downloaded file can be deleted.

Opening an AppImage older than the installed version changes nothing: it says so and offers to open the installed
one.

### Uninstall

From the app: Settings › Storage › **Erase everything**, with the **engine** box ticked (and the **models** box to
also remove StreetCLIP and PLONK, 1.8 GB). This removes your settings, your API key, your data, the keyboard
shortcuts, the applications-menu entry, the engine and the installed copy of the application. Only the AppImage you
downloaded is left, if you kept it: delete it.

If the app no longer starts, close it, then remove the same things by hand (default folders; yours differ if you set
`XDG_DATA_HOME`, `XDG_CONFIG_HOME` or `HF_HOME`):

```sh
rm -rf ~/.local/share/geonesclick ~/.config/geonesclick
rm -f ~/.local/share/applications/fr.mrnesclick.geonesclick.desktop \
      ~/.local/share/icons/hicolor/*/apps/fr.mrnesclick.geonesclick.png
rm -rf ~/.cache/huggingface/hub/models--geolocal--StreetCLIP \
       ~/.cache/huggingface/hub/models--nicolas-dufour--PLONK_OSV_5M
```

and delete the two shortcuts "GeoNesClick – capture" and "GeoNesClick – marks" in GNOME's Settings › Keyboard ›
Custom Shortcuts.

## Use

1. Open a GeoGuessr game in your browser and start GeoNesClick. The first time, GNOME asks which window to share:
   choose your browser window.
2. During a round, press **Super+Shift+G**: the coach shows the help of the chosen level.
3. To read a sign, press **Super+Shift+Z** and draw a box around it.

## Help levels

| Level | What is shown |
|---|---|
| 1. Look | where to look, without naming a country |
| 2. Clues | + what the AI sees, including the text read word for word |
| 3. Countries | + likely countries, map, Plonk It tips |
| 4. Answer (default) | + the answer: country, region if a text names it, and the proof |

## What GeoNesClick downloads

Every network access is listed in [`downloads.toml`](engine/src/geonesclick/downloads.toml) and shown by the app
before anything is downloaded. Options can be turned off in the Settings.

| What | From where | Size | Licence | When | What leaves your machine |
|---|---|---|---|---|---|
| Python 3.12 **(required)** | `github.com`, `objects.githubusercontent.com` | 30 MB | PSF-2.0 | once, at installation | — |
| Python libraries (PyTorch, Transformers, FastAPI…) **(required)** | `pypi.org`, `files.pythonhosted.org` | 3.1 GB with an NVIDIA card, 70 MB without | various (BSD, MIT, Apache-2.0…) | once, at installation | — |
| PyTorch for the processor, without an NVIDIA card **(required)** | `download.pytorch.org` | 200 MB | BSD-3-Clause | once, at installation | — |
| StreetCLIP model **(required)** | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 1.7 GB | CC BY-NC 4.0 (non-commercial) | once, at installation | — |
| GeoNames places directory and region names | `download.geonames.org` | 11 MB | CC BY 4.0 | once, if you accept it | — |
| Villages of the leading country (GeoNames) | `download.geonames.org` | 8 MB | CC BY 4.0 | on demand | — |
| Plonk It guides | `www.plonkit.net` | 2 MB | for your personal use, never redistributed | if you accept it: once, then the changed guides every 30 days | — |
| PLONK model | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 144 MB | MIT | once, if you accept it | — |
| NVIDIA vision model (online API) | `integrate.api.nvidia.com` | — | NVIDIA API terms; your key | on every use | your captures without the browser's bars (shrunk to 1,280 px), the crops of your marks, the Plonk It tips to classify and translate |
| OpenStreetMap map tiles | `tile.openstreetmap.org` | — | ODbL; OSMF tile policy | on every use | your IP address and the map areas shown |

## Privacy

- The engine runs on your machine and only answers the coach window: no website or other computer can reach it.
- Your captures leave your machine only for the NVIDIA vision model, and only if you gave an API key (see the
  table above). The browser's bars (tab titles, address, bookmarks) are cut off first.
- Your API key is stored in a file readable by you only.
- Settings › Storage › **Erase everything** removes all your data, and the engine if you wish.

## Documentation

- [How it works](docs/how-it-works.md): the Answer card, marks, local rules, what is certain, metas, Plonk It, map
- [Architecture](docs/architecture.md): the Rust, Vue and Python parts and how they talk to each other
- [Configuration](docs/configuration.md): `config.toml`, settings, debug mode
- [Measurements and benchmarks](docs/benchmarks.md): why each technical choice was made, and tests
- [Maintenance](docs/maintenance.md): updates, where the data is, tools and licences
- [Development](docs/development.md): build from source, build the AppImage, run the tests
- [Compatibility](docs/compatibility.md): what GeoNesClick needs, the systems tested and reported
- [Changelog](CHANGELOG.md): what changes from one version to the next
- [Contributing](CONTRIBUTING.md) and [Security](SECURITY.md): how to help, how to report a vulnerability

## License

Code under [Apache-2.0](LICENSE) © 2026 MrNesClick. The StreetCLIP model is under **CC BY-NC 4.0**: no commercial
use of the coach.

[report]: https://github.com/MrNesClick/GeoNesClick/issues/new?template=system-report.yml
