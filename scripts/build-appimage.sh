#!/usr/bin/env bash
# Builds the GeoNesClick AppImage. To run on Ubuntu 24.04 (the oldest target: what is compiled here
# works on the later versions), after scripts/install.sh.
#
# A LIGHT AppImage (~100 MB: the UI + uv) that installs the engine
# on first launch, with an assistant that first shows EVERYTHING that will be downloaded. It bundles:
#   - uv (pinned version, hash checked): it installs Python and the dependencies, without touching the system;
#   - the engine as a wheel, and PyGObject + pycairo compiled here (they only exist as sources: without this, every
#     user would need a compiler);
#   - the pinned dependencies WITH hashes, in two variants (PyTorch CUDA if there is an NVIDIA card, otherwise CPU);
#   - the list of downloads and the detailed list of packages (name, version, size, licence).
#
# Usage: scripts/build-appimage.sh                 → app/src-tauri/target/release/bundle/appimage/GeoNesClick_*.AppImage
#        scripts/build-appimage.sh --engine-only   → only app/src-tauri/engine-bundle/ (steps 1 to 4)
set -euo pipefail
ENGINE_ONLY=0
[[ "${1:-}" == "--engine-only" ]] && ENGINE_ONLY=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/app/src-tauri/engine-bundle"      # AppImage resources (ignored by git)
UV_VERSION="0.9.17"                          # the one used by the tests; change with care (docs/maintenance.md)
UV_ARCHIVE="uv-x86_64-unknown-linux-gnu.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_ARCHIVE}"

step() { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }
# GitHub release downloads can answer 504 for many minutes (three failed release builds): retried with
# a doubling delay, for up to 15 minutes per file.
fetch() { curl -fsSL --retry 10 --retry-max-time 900 --max-time 300 -o "$1" "$2"; }

# Tools that Tauri's AppImage bundler downloads itself, once and with no retry, unless they are already in its cache
# (crates/tauri-bundler/src/bundle/linux/appimage/linuxdeploy.rs at tag tauri-cli-v2.12.4; recheck the names on a CLI
# upgrade, or Tauri downloads them again itself, without retry). Fetched here into that cache.
# The AppImage plugin comes from a "continuous" release that changes upstream: no hash to pin. It is required here,
# whereas Tauri falls back to an older built-in runtime without it, not the one tested on a clean Ubuntu.
TAURI_TOOLS="${XDG_CACHE_HOME:-$HOME/.cache}/tauri"
TOOLS_BASE="https://github.com/tauri-apps/binary-releases/releases/download"
APPIMAGE_TOOLS=(  # file in the cache | URL | sha256 (empty: not pinned)
  "AppRun-x86_64|$TOOLS_BASE/apprun-old/AppRun-x86_64|f30140a43a0a59e46db21bdefdf749b9e9f2c6946e92afabbacf98b8ae73fb4f"
  "linuxdeploy-07333c6-x86_64.AppImage|$TOOLS_BASE/linuxdeploy-07333c6/linuxdeploy-x86_64.AppImage|36a2d7e274d12e1050d0e9ecfe11d339ed54720b2bec464c286d53f8b07f5c62"
  "linuxdeploy-plugin-appimage.AppImage|https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage|"
)
# The runtime embedded in the AppImage, run on every launch. Without it, appimagetool (inside the plugin) downloads it
# itself while bundling, with no retry (most likely what failed a v0.1.1 build: Tauri hides linuxdeploy's output).
# Pinned to the one shipped in v0.1.0 (build ID ef655b05), validated on a clean Ubuntu 26.04, although upstream
# publishes it as "continuous" (docs/maintenance.md).
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
RUNTIME_SHA256="617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46"

[[ "$(. /etc/os-release && echo "$ID $VERSION_ID")" == "ubuntu 24.04" ]] \
  || echo "  ! not on Ubuntu 24.04: the compiled packages might not work on an older version"

rm -rf "$OUT" && mkdir -p "$OUT/wheels"
TMP="$(mktemp -d)" && trap 'rm -rf "$TMP"' EXIT

step "1. uv ${UV_VERSION} (hash checked)"
fetch "$TMP/$UV_ARCHIVE" "$UV_URL"
fetch "$TMP/$UV_ARCHIVE.sha256" "$UV_URL.sha256"
(cd "$TMP" && sha256sum -c "$UV_ARCHIVE.sha256" >/dev/null) && ok "hash matches"
tar -xzf "$TMP/$UV_ARCHIVE" -C "$TMP"
install -m 0755 "$TMP/uv-x86_64-unknown-linux-gnu/uv" "$OUT/uv"

step "2. Engine (wheel)"
(cd "$ROOT/engine" && uv build --wheel --out-dir "$OUT/wheels" >/dev/null)
ok "$(cd "$OUT/wheels" && ls geonesclick-*.whl)"

step "3. PyGObject and pycairo, compiled here"
# PyPI sources checked against the uv.lock hashes (the same as in development) before compiling.
python3 - "$ROOT/engine/uv.lock" > "$TMP/sources.txt" <<'PY'
import sys, tomllib
for p in tomllib.load(open(sys.argv[1], "rb"))["package"]:
    if p["name"] in ("pygobject", "pycairo"):
        print(f"{p['name']}=={p['version']} --hash={p['sdist']['hash']}")
PY
uv tool run --python 3.12 --from "pip==25.3" pip wheel --no-deps --no-binary :all: --require-hashes --quiet \
  -r "$TMP/sources.txt" --wheel-dir "$OUT/wheels"
ok "$(cut -d' ' -f1 "$TMP/sources.txt" | tr '\n' ' ')(hashes checked)"

step "4. Pinned dependencies and detailed list"
"$ROOT/engine/.venv/bin/python" -I "$ROOT/scripts/bundle_meta.py" "$OUT"
install -m 0755 "$ROOT/scripts/install-engine.sh" "$OUT/install-engine.sh"
grep -m1 '^version' "$ROOT/engine/pyproject.toml" | cut -d'"' -f2 > "$OUT/VERSION"
# An update shows what changed since the installed version, in the UI's language (CHANGELOG.<lang>.md, English otherwise).
install -m 0644 "$ROOT"/CHANGELOG*.md "$OUT/"
ok "version $(cat "$OUT/VERSION")"

((ENGINE_ONLY)) && { du -sh "$OUT"; exit 0; }

step "5. AppImage (Tauri)"
mkdir -p "$TAURI_TOOLS"
for tool in "${APPIMAGE_TOOLS[@]}"; do
  IFS='|' read -r name url sha <<< "$tool"
  [[ -e "$TAURI_TOOLS/$name" ]] && continue  # Tauri edits linuxdeploy in place after use: a cached copy is not rehashed
  fetch "$TMP/$name" "$url"
  [[ -z "$sha" ]] || echo "$sha  $TMP/$name" | sha256sum -c --quiet
  install -m 0755 "$TMP/$name" "$TAURI_TOOLS/$name"
  ok "$name${sha:+ (hash checked)}"
done
fetch "$TMP/runtime-x86_64" "$RUNTIME_URL"
echo "$RUNTIME_SHA256  $TMP/runtime-x86_64" | sha256sum -c --quiet \
  || { echo "  ! the AppImage runtime changed upstream: test the new one, then update RUNTIME_SHA256"; exit 1; }
export LDAI_RUNTIME_FILE="$TMP/runtime-x86_64"  # read by linuxdeploy-plugin-appimage, passed to appimagetool
ok "AppImage runtime (hash checked)"
cd "$ROOT/app"
pnpm tauri build --bundles appimage --config src-tauri/tauri.appimage.conf.json
ls -lh src-tauri/target/release/bundle/appimage/*.AppImage
