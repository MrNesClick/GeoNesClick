[← README](../README.md)

# Development

## Requirements

On top of the [user requirements](../README.md#requirements): [Rust](https://rustup.rs),
[Node.js](https://nodejs.org) with [pnpm](https://pnpm.io), and [uv](https://docs.astral.sh/uv/). The system packages
(WebKitGTK for Tauri, GStreamer and PipeWire for the capture, headers to compile PyGObject) are checked by the
installation script.

## Build from source and run

```bash
scripts/install.sh                  # checks everything and installs the project's dependencies
scripts/install.sh --with-apt       # also installs the missing system packages (asks for sudo)
scripts/install.sh --setup-shortcut # adds the GNOME shortcuts: capture (Super+Shift+G), marks (Super+Shift+Z)
cd app && pnpm tauri dev            # starts the coach; it starts and stops the engine (engine/.venv)
```

To run the engine alone (without the UI): `cd engine && .venv/bin/python -m geonesclick`.

## Details

`scripts/install.sh` can safely be run again, for example after each `git pull`. On first launch, enter your NVIDIA API
key (free on [build.nvidia.com](https://build.nvidia.com), "Get API Key") in **Settings › Analysis**. It is stored
outside the repository, in `~/.config/geonesclick/nvapi.key`, readable by you only (0600), and is never shown again
(only its last 4 characters). The `NVAPI` environment variable, if set, takes priority. A key still in the old
`.env` is **moved** there at startup (the line is removed from the `.env`).

To change the shortcuts: `GNC_SHORTCUT="<Super><Shift>h" GNC_MARK_SHORTCUT="<Super><Shift>m"
scripts/install.sh --setup-shortcut`. The shortcuts are written with `/usr/bin/gsettings`: a third-party `gsettings`
(Linuxbrew) may not write to the GNOME settings.

The engine uses a **Python 3.12 managed by uv**, in a virtual environment **isolated** from the system packages. The
GStreamer bindings (PyGObject) are compiled from PyPI at installation, hence the `libgirepository-2.0-dev` and
`libcairo2-dev` packages. Only the GStreamer description files (`gir1.2-*`) come from the system.

## Translations

Everything the player sees comes from one catalog per language, `engine/src/geonesclick/locales/<lang>.json`, read
by the three layers: the engine (`geonesclick/i18n.py`), the UI (`app/src/i18n.ts`) and the installer
(`app/src-tauri/src/i18n.rs`, compiled in). Flat keys, `{name}` placeholders, plurals as `<key>.one` / `<key>.other`;
a missing key or language falls back to English. The language is `[coach] language` (`en` by default), chosen on the
installer's first screen and in the Settings. `en.json` is the reference; `tests/test_i18n.py` checks that every
catalog has the same keys and placeholders, and that every key used in the code exists. To add a language, add its
file: the three layers find it (a language outside en, fr, es, de, it, pt also goes into `[coach] language` in
`config.py`).

## Build the AppImage

```bash
scripts/build-appimage.sh                 # → app/src-tauri/target/release/bundle/appimage/GeoNesClick_*.AppImage
scripts/build-appimage.sh --engine-only   # only app/src-tauri/engine-bundle/ (steps 1 to 4)
```

Run it on Ubuntu 24.04, the oldest target: what is compiled there works on the later versions. The AppImage stays
light (~100 MB: the UI and uv) and bundles the engine as a wheel, PyGObject and pycairo compiled for it, the pinned
dependencies with their hashes (CUDA and CPU variants) and the list of downloads. The engine itself is installed by
the first-launch assistant, with `install-engine.sh`, once the user has accepted the list. Each download is tried 6
times (`UV_HTTP_RETRIES=5`, huggingface_hub's own retries); on failure, `diagnose` in `setup.rs` reads the script's
last error lines and tells the user which site does not answer (from the URL, else the phase) or that the disk is
full; the uv and Hugging Face caches are kept, so "Retry" resumes.

The app icon's source is `app/src-tauri/icons/icon.svg`; after changing it, regenerate the bundled sizes with
`pnpm tauri icon src-tauri/icons/icon.svg -o <folder>` (from `app/`) and copy back only the files already in
`app/src-tauri/icons/` (the command also makes Android and iOS icons, unused here).

## Publish a release

Releases are built by GitHub Actions ([release.yml](../.github/workflows/release.yml)), never from a developer's
machine. Write the version's section in [CHANGELOG.md](../CHANGELOG.md) (move the `[Unreleased]` items under
`## [x.y.z] - date`, written for the people who use the app), bump the version in the four manifests
(`engine/pyproject.toml`, `app/package.json`, `app/src-tauri/Cargo.toml`, `app/src-tauri/tauri.conf.json`) and the
two lock files, commit, then push an annotated tag:

```bash
git tag -a v0.2.0 -m "GeoNesClick 0.2.0" && git push origin v0.2.0
```

The workflow checks that the tag matches the four versions and that CHANGELOG.md has a section for it
(`scripts/release-notes.sh 0.2.0` prints it), runs the tests, builds the AppImage on Ubuntu 24.04 and publishes
the release with the AppImage, its SHA-256 checksum and that section as release notes.

## Tests

From the repository root; no network access, no display:

```bash
(cd engine && .venv/bin/python -m pytest -q)   # engine
(cd app && npx vue-tsc --noEmit)               # UI type check
(cd app/src-tauri && cargo test --lib)         # installer and Tauri side
```

Before each commit: the tests, then a code review and a security review. The benchmarks are described in
[benchmarks.md](benchmarks.md).
