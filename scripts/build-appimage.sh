#!/usr/bin/env bash
# Fabrique l'AppImage de GeoNesClick. À lancer sur Ubuntu 24.04 (la plus ancienne cible : ce qui est compilé ici
# fonctionne sur les versions suivantes), après scripts/install.sh.
#
# Décidé avec l'utilisateur le 2026-11-07 : une AppImage LÉGÈRE (~100 Mo : l'interface + uv) qui installe le moteur
# au premier lancement, avec un assistant qui montre d'abord TOUT ce qui sera téléchargé. Elle embarque :
#   - uv (version figée, empreinte vérifiée) : il installe Python et les dépendances, sans rien toucher au système ;
#   - le moteur en wheel, et PyGObject + pycairo compilés ici (ils n'existent qu'en sources : sans cela, chaque
#     utilisateur devrait avoir un compilateur) ;
#   - les dépendances figées AVEC empreintes, en deux variantes (PyTorch CUDA si carte NVIDIA, sinon CPU) ;
#   - la liste des téléchargements et la liste détaillée des paquets (nom, version, taille, licence).
#
# Usage : scripts/build-appimage.sh                 → app/src-tauri/target/release/bundle/appimage/GeoNesClick_*.AppImage
#         scripts/build-appimage.sh --engine-only   → seulement app/src-tauri/engine-bundle/ (étapes 1 à 4)
set -euo pipefail
ENGINE_ONLY=0
[[ "${1:-}" == "--engine-only" ]] && ENGINE_ONLY=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/app/src-tauri/engine-bundle"      # ressources de l'AppImage (ignorées par git)
UV_VERSION="0.9.17"                          # celle des tests ; à changer avec soin (README, Maintenance)
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
# Sources de PyPI vérifiées par les empreintes de uv.lock (les mêmes que le développement) avant compilation.
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
grep -m1 '^version' "$ROOT/engine/pyproject.toml" | cut -d'"' -f2 > "$OUT/VERSION"
ok "version $(cat "$OUT/VERSION")"

((ENGINE_ONLY)) && { du -sh "$OUT"; exit 0; }

step "5. AppImage (Tauri)"
cd "$ROOT/app"
pnpm tauri build --bundles appimage --config src-tauri/tauri.appimage.conf.json
ls -lh src-tauri/target/release/bundle/appimage/*.AppImage
