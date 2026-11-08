#!/usr/bin/env bash
# Prepares the PLONK benchmark (engine/spikes/plonk_bench.py), without installing anything in the engine's venv.
#
# Usage: scripts/setup-plonk-spike.sh      (after scripts/install.sh; safe to run again)
#
# Everything goes to engine/spikes/.vendor/ (ignored by git):
#   plonk/   PLONK code (MIT) pinned to a precise commit
#   deps/    einops, geoopt, torchdiffeq, scipy, installed without their dependencies (torch and numpy
#            come from the engine's venv)
#   ne_50m_admin_0_countries.geojson   Natural Earth 1:50m borders (public domain)
# The PLONK_OSV_5M weights (safetensors, 144 MB) are downloaded by the bench into the Hugging Face cache.
# To remove everything: rm -rf engine/spikes/.vendor
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/engine/spikes/.vendor"
PY="$ROOT/engine/.venv/bin/python"

PLONK_REPO="https://github.com/nicolas-dufour/plonk"
PLONK_COMMIT="76d46410910c9dfec9e19ed371450ebc7051cdf3"  # 2025-09-29
DEPS=(einops==0.8.2 geoopt==0.5.1 torchdiffeq==0.2.5 scipy==1.18.1)
NE_URL="https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_50m_admin_0_countries.geojson"

ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; exit 1; }

[[ -x "$PY" ]] || fail "engine venv missing: run scripts/install.sh first"
mkdir -p "$VENDOR"

# PLONK code, pinned: we check that the commit obtained is indeed the expected one.
if [[ "$(git -C "$VENDOR/plonk" rev-parse HEAD 2>/dev/null)" != "$PLONK_COMMIT" ]]; then
  rm -rf "$VENDOR/plonk"
  git init -q "$VENDOR/plonk"
  git -C "$VENDOR/plonk" fetch -q --depth 1 "$PLONK_REPO" "$PLONK_COMMIT"
  git -C "$VENDOR/plonk" checkout -q FETCH_HEAD
fi
[[ "$(git -C "$VENDOR/plonk" rev-parse HEAD)" == "$PLONK_COMMIT" ]] || fail "unexpected PLONK commit"
ok "PLONK code ${PLONK_COMMIT:0:7}"

uv pip install -q --python "$PY" --target "$VENDOR/deps" --no-deps "${DEPS[@]}"
ok "dependencies: ${DEPS[*]}"

if [[ ! -s "$VENDOR/ne_50m_admin_0_countries.geojson" ]]; then
  curl -sSfL -o "$VENDOR/ne_50m_admin_0_countries.geojson.part" "$NE_URL"
  mv "$VENDOR/ne_50m_admin_0_countries.geojson.part" "$VENDOR/ne_50m_admin_0_countries.geojson"
fi
ok "Natural Earth v5.1.2 borders"

printf '\nReady. Run: cd engine && .venv/bin/python spikes/plonk_bench.py\n'
