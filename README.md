**English** | [Français](README.fr.md)

# GeoNesClick

AI-assisted geolocation coach for OSINT and GeoGuessr training. Press a shortcut during a round: the coach looks at
the view on your screen and points you to the useful clues, with as much help as you choose.

> **For training only** (solo games, unranked maps). The coach only reads the image on screen, never the game's
> data. GeoGuessr's rules forbid third-party tools in ranked games: do not use it in competition.

## Features

- **Four help levels**, from "where to look" to the full answer with its proof.
- **Local AI** (StreetCLIP) for the likely countries in about 60 ms, plus a remote vision model that reads the text
  in the view.
- **Marks**: circle a sign or a shop front, and the coach reads it and draws local, sourced conclusions from it.
- **Map** of the likely zones (PLONK, computed locally) and of the places read on your signs.
- **Progress tracking**: after each round, "Where was it?" records the real country and shows your confusions.
- Everything is configurable from the app, and everything it downloads is listed before the first byte.

The interface is in French for now.

## Requirements

- Ubuntu 24.04 or later with GNOME (Wayland or Xorg)
- An NVIDIA card with CUDA (recommended; StreetCLIP also runs on the CPU, more slowly)
- [Rust](https://rustup.rs), [Node.js](https://nodejs.org) with [pnpm](https://pnpm.io), and [uv](https://docs.astral.sh/uv/)
- A free NVIDIA API key from [build.nvidia.com](https://build.nvidia.com)

## Install and run

```bash
scripts/install.sh --with-apt --setup-shortcut   # dependencies, system packages, GNOME shortcuts
cd app && pnpm tauri dev                         # starts the coach (and its engine)
```

On first launch, choose the browser window you play in, then enter your API key in **Settings › Analysis**
(*Réglages › Analyse*). During a round, press **Super+Shift+G** to capture, **Super+Shift+Z** to mark clues.

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
| Python libraries (PyTorch, Transformers, FastAPI…) **(required)** | `pypi.org`, `files.pythonhosted.org` | 3.1 GB | various (BSD, MIT, Apache-2.0…) | once, at installation | — |
| PyTorch for CPU, if there is no NVIDIA card **(required)** | `download.pytorch.org` | 200 MB | BSD-3-Clause | once, at installation | — |
| StreetCLIP model **(required)** | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 1.7 GB | CC BY-NC 4.0 (non-commercial) | once, at installation | — |
| GeoNames places directory | `download.geonames.org` | 11 MB | CC BY 4.0 | once, if you accept it | — |
| Villages of the leading country (GeoNames) | `download.geonames.org` | 8 MB | CC BY 4.0 | on demand | — |
| Plonk It guides | `www.plonkit.net` | 2 MB | for your personal use, never redistributed | once, if you accept it | — |
| PLONK model | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 144 MB | MIT | once, if you accept it | — |
| NVIDIA vision model (online API) | `integrate.api.nvidia.com` | — | NVIDIA API terms; your key | on every use | your captures (1,280 px), your marks, tips to translate |
| OpenStreetMap map tiles | `tile.openstreetmap.org` | — | ODbL; OSMF tile policy | on every use | your IP address and the map areas shown |

## Privacy

- The engine only listens on `127.0.0.1` and refuses any other origin.
- Your API key is stored in `~/.config/geonesclick/nvapi.key`, readable by you only, never in the repository.
- Settings › Storage › **Erase everything** (*Tout effacer*) removes all your data in one go.

## Documentation

- [How it works](docs/how-it-works.md): marks, local rules, locks, metas, Plonk It, map, architecture
- [Configuration](docs/configuration.md): `config.toml`, settings, debug mode
- [Measurements and benchmarks](docs/benchmarks.md): why each technical choice was made, and tests
- [Maintenance](docs/maintenance.md): updates, where the data is, tools and licences

## License

Code under [Apache-2.0](LICENSE) © 2026 MrNesClick. The StreetCLIP model is under **CC BY-NC 4.0**: no commercial
use of the coach.
