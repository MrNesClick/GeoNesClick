[← README](../README.md)

# Maintenance

## Installation details

The script can safely be run again, for example after each `git pull`. Then, on first launch, enter your NVIDIA API
key (free on [build.nvidia.com](https://build.nvidia.com), "Get API Key") in **Settings › Analysis**
(*Réglages › Analyse*). It is stored outside the repository, in `~/.config/geonesclick/nvapi.key`, readable by you
only (0600), and is never shown again (only its last 4 characters). The `NVAPI` environment variable, if set, takes
priority. A key still in the old `.env` is **moved** there at startup (the line is removed from the `.env`).

To change the shortcuts: `GNC_SHORTCUT="<Super><Shift>h" GNC_MARK_SHORTCUT="<Super><Shift>m"
scripts/install.sh --setup-shortcut`.

The engine uses a **Python 3.12 managed by uv**, in a virtual environment **isolated** from the system packages. The
GStreamer bindings (PyGObject) are compiled from PyPI at installation, hence the `libgirepository-2.0-dev` and
`libcairo2-dev` packages. Only the GStreamer description files (`gir1.2-*`) come from the system.

## Shared window

The coach window starts the Python engine and stops it when closed. The first time, GNOME asks which window to
share: choose the browser window where you play. The permission is remembered
(`~/.config/geonesclick/screencast.token`). To change it (another browser, screen or resolution), open the
**Settings** tab and click **Change window** (*Changer de fenêtre*, Captures section): the GNOME picker opens again.

To run the engine alone (without the UI): `cd engine && .venv/bin/python -m geonesclick`.

## Updates and data

**Update**: `git pull`, then `scripts/install.sh` (safe to run again: it re-syncs the venv with `uv.lock` and the
front end with `pnpm-lock.yaml`). For the PLONK bench, also run `scripts/setup-plonk-spike.sh` again.

**Change a version**:
- Python dependencies: `cd engine && uv add <package>==<version>` (updates `pyproject.toml` and `uv.lock`), then
  `.venv/bin/python -m pytest -q`;
- front-end dependencies: `cd app && pnpm update <package>`;
- PLONK bench: change `PLONK_COMMIT` and `DEPS` at the top of `scripts/setup-plonk-spike.sh`, run the script again
  then the bench.

**Where the data is** (none of it is versioned):

| Location | Content | If deleted |
|---|---|---|
| `~/.config/geonesclick/config.toml` | your settings | back to the default values |
| `~/.config/geonesclick/mes-metas.toml` | your metas and verdicts on the seed | lost: back it up |
| `~/.config/geonesclick/screencast.token` | GNOME sharing permission | GNOME asks for the window again |
| `~/.local/share/geonesclick/plonkit/` | Plonk It guides, tips, vectors, translations | rebuilt at startup (~3 min, translations redone on demand) |
| `~/.local/share/geonesclick/places/` | GeoNames places directory (CC BY 4.0), indexed | downloaded again at startup if missing (~11 MB) |
| `~/.cache/huggingface/hub/` | StreetCLIP and PLONK weights | downloaded again at the next launch (network required) |
| `~/.local/share/geonesclick/dataset/` | test set (images, `labels.toml`, the bench's `rounds/`) | lost: back it up, it is the basis of all the measurements |
| `~/.local/share/geonesclick/captures/` | round captures; in debug mode, the `capture-<id>.json` log of each analysis | no consequence |
| `engine/spikes/.vendor/` | code and dependencies of the PLONK bench | `scripts/setup-plonk-spike.sh` recreates it |

The test set and the captures lived in `engine/` until 2026-11-07 (read-only in an AppImage): on first launch, the
captures are moved and the test set copied (the copy tracked by git stays in the repository).

**Settings › Storage** (*Stockage*) shows the size of each item and an **Empty** button (*Vider*, in two steps:
Empty, then Confirm, with what it costs; Plonk It warns that the ahead-of-time translations will have to be redone).
The maximum size (`[storage] max_cache_mb`, 500 MB) only applies to the caches **that grow** on their own (villages
of the countries met): the least recently used go first. The base (GeoNames directory, Plonk It guides) never goes
on its own, and your test set, your metas and your config are never emptied. For safety, only files known to the
coach are deleted, never a whole folder.

**Erase everything** (*Tout effacer*, right to erasure, GDPR): at the bottom of Settings › Storage. The list of what
goes is shown with the sizes: API key, settings, your metas, screen-sharing permission, captures and logs, test set
(flagged as precious), Plonk It guides and translations, GeoNames places and villages, UI state, the app's GNOME
shortcuts. A separate box, unticked: also the downloaded models (StreetCLIP, PLONK: nothing personal; other
software's models stay). You have to type "EFFACER"; then the engine and the UI start again from scratch. Only files
known to the app are deleted, never a folder set by hand nor its foreign content. The copy of the test set
versioned in the repository (`engine/dataset/`) is not touched.

**Offline**: once StreetCLIP and PLONK (if enabled) are cached, the engine switches Hugging Face to offline mode at
startup. To get a new version of a model, delete its folder
(`~/.cache/huggingface/hub/models--geolocal--StreetCLIP`, `models--nicolas-dufour--PLONK_OSV_5M`) and restart.

**Update PLONK or Natural Earth**: the weights are pinned to a Hugging Face revision (`[plonk] revision`, the one
that was measured); to change it, replace `revision`, run `spikes/plonk_bench.py` again and compare. The PLONK
network code is pinned in `plonk.py` (commit 76d4641); after a change in the original repository, redo the bench
(`scripts/setup-plonk-spike.sh` with the new commit, then `spikes/plonk_bench.py`) and compare with the engine's
module before modifying it. The outlines come from Natural Earth v5.1.2; for another version, replace
`engine/src/geonesclick/data/ne_50m_admin_0_countries.geojson` (the `ISO_A2_EH` field must exist) and run the tests
again.

**Before each commit**: the tests (`cd engine && .venv/bin/python -m pytest -q`, without any network access), then a
code review and a security review.

## Tools and licences

**GeoNesClick code: [Apache-2.0](../LICENSE) licence** (© 2026 MrNesClick). The models and data downloaded on first
launch keep their own licence (see [What GeoNesClick downloads](../README.md#what-geonesclick-downloads)): in particular **StreetCLIP is under CC BY-NC 4.0,
non-commercial use**, which applies to any use of the app that relies on it.

| Tool | Role | Licence or terms |
|---|---|---|
| [Tauri 2](https://v2.tauri.app), [Vue 3](https://vuejs.org), [Tailwind 4](https://tailwindcss.com) | coach window | MIT / Apache-2.0 |
| [FastAPI](https://fastapi.tiangolo.com), Uvicorn | the engine's local server | MIT / BSD-3 |
| GStreamer, PipeWire, ScreenCast portal (PyGObject) | window capture | LGPL |
| [PyTorch](https://pytorch.org), [Transformers](https://github.com/huggingface/transformers) | running StreetCLIP | BSD-3 / Apache-2.0 |
| [StreetCLIP](https://huggingface.co/geolocal/StreetCLIP) (`geolocal/StreetCLIP`) | level 1, likely countries | **CC BY-NC 4.0: no commercial use** |
| [NVIDIA API](https://build.nvidia.com), Nemotron 3.5 Super VL | level 2, clue sheet | NVIDIA terms of service, personal key |
| SQLite FTS5 | search in the tips | public domain |
| [Plonk It](https://www.plonkit.net) | guides per country | collected locally for your use, never redistributed |
| [PLONK](https://github.com/nicolas-dufour/plonk) (`PLONK_OSV_5M`) | cloud of positions for the map (reduced code bundled) | MIT (code and weights); trained on OSV-5M, Mapillary images CC BY-SA 4.0 |
| [Natural Earth](https://www.naturalearthdata.com) 1:50m | country outlines, country of a point | public domain |
| [Leaflet](https://leafletjs.com) 1.9.4 | the UI's map | BSD-2 |
| [OpenStreetMap tiles](https://www.openstreetmap.org/copyright) | map background, online | ODbL data, attribution required; [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) |
| [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io), [cargo](https://rustup.rs) | installation | MIT / Apache-2.0 |

StreetCLIP's licence alone forbids any commercial use of the coach.
