[← README](../README.md)

# Maintenance

## Shared window

The coach window starts the Python engine and stops it when closed. The first time, GNOME asks which window to
share: choose the browser window where you play. The permission is remembered
(`~/.config/geonesclick/screencast.token`). To change it (another browser, screen or resolution), open the
**Settings** tab and click **Change window** (Capture section): the GNOME picker opens again. If you stop the
sharing from GNOME's indicator, the coach says so and offers **Restart sharing**, which also opens the picker; only
the app's start resumes the remembered window without asking.

## Updates and data

**Update (from source)**: `git pull`, then `scripts/install.sh` (safe to run again: it re-syncs the venv with
`uv.lock` and the front end with `pnpm-lock.yaml`). For the PLONK bench, also run `scripts/setup-plonk-spike.sh` again.

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
| `~/.config/geonesclick/my-metas.toml` | your metas and verdicts on the seed | lost: back it up |
| `~/.config/geonesclick/screencast.token` | GNOME sharing permission | GNOME asks for the window again |
| `~/.local/share/geonesclick/plonkit/` | Plonk It guides, tips, vectors, translations | rebuilt at startup (a few minutes; the translations are redone ahead of time) |
| `~/.local/share/geonesclick/places/` | GeoNames places directory (CC BY 4.0), indexed | downloaded again at startup if missing (~11 MB) |
| `~/.cache/huggingface/hub/` | StreetCLIP and PLONK weights | downloaded again at the next launch (network required) |
| `~/.local/share/geonesclick/dataset/` | test set (images, `labels.toml`, the bench's `rounds/`) | lost: back it up, it is the basis of all the measurements |
| `~/.local/share/geonesclick/captures/` | round captures; in debug mode, the `capture-<id>.json` log of each analysis | no consequence |
| `engine/spikes/.vendor/` | code and dependencies of the PLONK bench | `scripts/setup-plonk-spike.sh` recreates it |

The test set and the captures lived in `engine/` in early versions (read-only in an AppImage): on first launch, the
captures are moved and the test set copied (the copy tracked by git stays in the repository).

**Settings › Storage** shows the size of each item and an **Empty** button (in two steps:
Empty, then Confirm, with what it costs; Plonk It warns that the ahead-of-time translations will have to be redone).
The maximum size (`[storage] max_cache_mb`, 500 MB) only applies to the caches **that grow** on their own (villages
of the countries met): the least recently used go first. The base (GeoNames directory, Plonk It guides) never goes
on its own, and your test set, your metas and your config are never emptied. For safety, only files known to the
coach are deleted, never a whole folder.

**Erase everything** (right to erasure, GDPR): at the bottom of Settings › Storage. The list of what
goes is shown with the sizes: API key, settings, your metas, screen-sharing permission, captures and logs, test set
(flagged as precious), Plonk It guides and translations, GeoNames places and villages, UI state, the app's GNOME
shortcuts. Two separate boxes, unticked: also the downloaded models (StreetCLIP, PLONK: nothing personal; other
software's models stay), and, with the AppImage, the engine installed in `~/.local/share/geonesclick/engine/`. You
have to type the word shown ("ERASE" in English). Then the engine and the UI start again from scratch; with the
engine box, GeoNesClick is uninstalled instead (with the models box too, only the AppImage is left), and opening
the AppImage again reinstalls the engine. Only files
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

**Update the AppImage runtime**: the program embedded at the head of the AppImage, run on every launch, is pinned
by its sha256 in `scripts/build-appimage.sh` (`RUNTIME_SHA256`), although upstream publishes it as
"continuous". When upstream publishes a new one, the build stops with "the AppImage runtime changed upstream": build
with the new hash, test the AppImage on a clean Ubuntu (no libfuse2), then commit the hash.

**Before each commit**: the three test suites (see [CONTRIBUTING.md](../CONTRIBUTING.md#before-you-send-a-change)),
then a code review and a security review.

## Tools and licences

**GeoNesClick code: [Apache-2.0](../LICENSE) licence** (© 2026 MrNesClick). The models and data downloaded on first
launch keep their own licence (see [What GeoNesClick downloads](../README.md#what-geonesclick-downloads)): in
particular **StreetCLIP is under CC BY-NC 4.0, non-commercial use**, which applies to any use of the app that relies
on it.

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
