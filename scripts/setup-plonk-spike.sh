#!/usr/bin/env bash
# Prépare le banc d'essai PLONK (engine/spikes/plonk_bench.py), sans rien installer dans le venv du moteur.
#
# Usage : scripts/setup-plonk-spike.sh      (après scripts/install.sh ; relançable sans risque)
#
# Tout va dans engine/spikes/.vendor/ (ignoré par git) :
#   plonk/   code de PLONK (MIT) figé sur un commit précis
#   deps/    einops, geoopt, torchdiffeq, scipy, installés sans leurs dépendances (torch et numpy
#            viennent du venv du moteur)
#   ne_50m_admin_0_countries.geojson   frontières Natural Earth 1:50m (domaine public)
# Les poids PLONK_OSV_5M (safetensors, 144 Mo) sont téléchargés par le banc dans le cache Hugging Face.
# Pour tout retirer : rm -rf engine/spikes/.vendor
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

[[ -x "$PY" ]] || fail "venv du moteur absent : lance d'abord scripts/install.sh"
mkdir -p "$VENDOR"

# Code PLONK, figé : on vérifie que le commit obtenu est bien celui attendu.
if [[ "$(git -C "$VENDOR/plonk" rev-parse HEAD 2>/dev/null)" != "$PLONK_COMMIT" ]]; then
  rm -rf "$VENDOR/plonk"
  git init -q "$VENDOR/plonk"
  git -C "$VENDOR/plonk" fetch -q --depth 1 "$PLONK_REPO" "$PLONK_COMMIT"
  git -C "$VENDOR/plonk" checkout -q FETCH_HEAD
fi
[[ "$(git -C "$VENDOR/plonk" rev-parse HEAD)" == "$PLONK_COMMIT" ]] || fail "commit PLONK inattendu"
ok "code PLONK ${PLONK_COMMIT:0:7}"

uv pip install -q --python "$PY" --target "$VENDOR/deps" --no-deps "${DEPS[@]}"
ok "dépendances : ${DEPS[*]}"

if [[ ! -s "$VENDOR/ne_50m_admin_0_countries.geojson" ]]; then
  curl -sSfL -o "$VENDOR/ne_50m_admin_0_countries.geojson.part" "$NE_URL"
  mv "$VENDOR/ne_50m_admin_0_countries.geojson.part" "$VENDOR/ne_50m_admin_0_countries.geojson"
fi
ok "frontières Natural Earth v5.1.2"

printf '\nPrêt. Lancer : cd engine && .venv/bin/python spikes/plonk_bench.py\n'
