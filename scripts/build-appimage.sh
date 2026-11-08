#!/usr/bin/env bash
# Builds the GeoNesClick AppImage. To run on Ubuntu 24.04 (the oldest target: what is compiled here
# works on the later versions), after scripts/install.sh.
#
# Decided with the user on 2026-11-07: a LIGHT AppImage (~100 MB: the UI + uv) that installs the engine
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
UV_VERSION="0.9.17"                          # the one used by the tests; change with care (README, Maintenance)
UV_ARCHIVE="uv-x86_64-unknown-linux-gnu.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_ARCHIVE}"

step() { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }

[[ "$(. /etc/os-release && echo "$ID $VERSION_ID")" == "ubuntu 24.04" ]] \
  || echo "  ! pas sur Ubuntu 24.04 : les paquets compilés pourraient ne pas marcher sur une version plus ancienne"

rm -rf "$OUT" && mkdir -p "$OUT/wheels"
TMP="$(mktemp -d)" && trap 'rm -rf "$TMP"' EXIT

step "1. uv ${UV_VERSION} (empreinte vérifiée)"
curl -fsSL -o "$TMP/$UV_ARCHIVE" "$UV_URL"
curl -fsSL -o "$TMP/$UV_ARCHIVE.sha256" "$UV_URL.sha256"
(cd "$TMP" && sha256sum -c "$UV_ARCHIVE.sha256" >/dev/null) && ok "empreinte conforme"
tar -xzf "$TMP/$UV_ARCHIVE" -C "$TMP"
install -m 0755 "$TMP/uv-x86_64-unknown-linux-gnu/uv" "$OUT/uv"

step "2. Moteur (wheel)"
(cd "$ROOT/engine" && uv build --wheel --out-dir "$OUT/wheels" >/dev/null)
ok "$(cd "$OUT/wheels" && ls geonesclick-*.whl)"

step "3. PyGObject et pycairo, compilés ici"
# PyPI sources checked against the uv.lock hashes (the same as in development) before compiling.
python3 - "$ROOT/engine/uv.lock" > "$TMP/sources.txt" <<'PY'
import sys, tomllib
for p in tomllib.load(open(sys.argv[1], "rb"))["package"]:
    if p["name"] in ("pygobject", "pycairo"):
        print(f"{p['name']}=={p['version']} --hash={p['sdist']['hash']}")
PY
uv tool run --python 3.12 --from "pip==25.3" pip wheel --no-deps --no-binary :all: --require-hashes --quiet \
  -r "$TMP/sources.txt" --wheel-dir "$OUT/wheels"
ok "$(cut -d' ' -f1 "$TMP/sources.txt" | tr '\n' ' ')(empreintes vérifiées)"

step "4. Dépendances figées et liste détaillée"
"$ROOT/engine/.venv/bin/python" -I "$ROOT/scripts/bundle_meta.py" "$OUT"
install -m 0755 "$ROOT/scripts/install-engine.sh" "$OUT/install-engine.sh"
grep -m1 '^version' "$ROOT/engine/pyproject.toml" | cut -d'"' -f2 > "$OUT/VERSION"
ok "version $(cat "$OUT/VERSION")"

((ENGINE_ONLY)) && { du -sh "$OUT"; exit 0; }

step "5. AppImage (Tauri)"
cd "$ROOT/app"
pnpm tauri build --bundles appimage --config src-tauri/tauri.appimage.conf.json
ls -lh src-tauri/target/release/bundle/appimage/*.AppImage
