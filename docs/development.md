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
machine. The work for a version lives on its branch (`work/0.2.0`), never on `main`; everything below happens on that
branch until the merge. Write the version's section in [CHANGELOG.md](../CHANGELOG.md) (move the `[Unreleased]` items under
`## [x.y.z] - date`, written for the people who use the app), and the same in [CHANGELOG.fr.md](../CHANGELOG.fr.md)
from `[Non publié]`. The section sets the number, strict SemVer: only `Fixed`
entries → PATCH; any `Added`, `Changed` or `Deprecated` → MINOR; anything that breaks (a setting or data file no
longer read without a migration, a raised system requirement, a removed feature) → MAJOR, or MINOR before 1.0.0. Then
bump the version in the four manifests (`engine/pyproject.toml`, `app/package.json`, `app/src-tauri/Cargo.toml`,
`app/src-tauri/tauri.conf.json`) and the two lock files, and commit. Build the AppImage and test it (above), then
fast-forward `main` to the branch and push it with an annotated tag:

```bash
git switch main && git merge --ff-only work/0.2.0
git tag -a v0.2.0 -m "GeoNesClick 0.2.0" && git push origin main v0.2.0
```

The run first waits for the repository owner to approve it (Actions tab › the run › **Review deployments**): the
`release` environment, limited to `v*` tags, requires that approval, so a pushed tag alone publishes nothing. The
workflow then checks that the tag matches the four versions, that CHANGELOG.md has a section for it
(`scripts/release-notes.sh 0.2.0` prints it) and that the number follows the rule above against the previous tag
(`scripts/check-version.py 0.2.0`, which gives the expected number otherwise, and also checks that CHANGELOG.fr.md
translates the section: same headings, same number of entries). It then runs the tests and the
interface tests, builds the AppImage on Ubuntu 24.04, installs the engine bundle it has just built on six systems
(`scripts/test-install.py`), and only then publishes the release with the AppImage, its SHA-256 checksum and that
section as release notes. A failure at any step publishes nothing.

## Tests

From the repository root; no network access, no display:

```bash
(cd engine && .venv/bin/python -m pytest -q)   # engine
(cd app && npx vue-tsc --noEmit)               # UI type check
(cd app/src-tauri && cargo test --lib)         # installer and Tauri side
(cd app && pnpm exec playwright test)          # interface, in WebKit (once: pnpm exec playwright install webkit)
```

The interface tests (`app/e2e/`) run the real Vue interface in WebKit, the engine of the Tauri window on Linux, with
the Rust side simulated by Tauri's mocks and the engine replayed from `app/e2e/fixtures/`. Those fixtures are written
by the real engine (`app/e2e/make_fixtures.py`, run from `engine/`); `tests/test_e2e_fixtures.py` fails when they no
longer match the engine's answers.

`scripts/test-install.py` installs the engine in fresh Docker containers of Ubuntu 24.04 and 26.04, Debian 13,
Fedora 45, Arch and openSUSE Tumbleweed, as the installer does: the system components under the installer's package
names (read from `setup.rs`), then `install-engine.sh`, then a StreetCLIP analysis (`scripts/install-smoke.py`). It
needs an engine bundle (`scripts/build-appimage.sh --engine-only`) and about 2 GB; the release workflow runs it on
the bundle it has just built.

Before each commit: the tests, then a code review and a security review. The benchmarks are described in
[benchmarks.md](benchmarks.md).
