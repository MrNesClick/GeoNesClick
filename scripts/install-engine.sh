#!/bin/sh
# Installs (or updates) the GeoNesClick engine from the AppImage: shipped in engine-bundle/ and run by
# the first-launch assistant, AFTER your consent to the list of downloads (downloads.toml).
# Can also be run by hand, without a UI (tests in a container):
#
#   install-engine.sh cuda|cpu [choices.json]
#
# Everything goes to ~/.local/share/geonesclick/engine/ (Python, cache, venv): nothing is installed in the system,
# and "Erase everything" can remove it all at once. The dependencies are checked by hash (--require-hashes).
# The engine is first installed alongside (venv.new) then swapped in at once: an interrupted installation never
# leaves a half-installed engine. Output readable by the assistant: "PHASE <name>" lines.
set -eu

B="$(cd "$(dirname "$0")" && pwd)"
VARIANT="${1:-}"
CHOICES="${2:-}"
case "$VARIANT" in cuda|cpu) ;; *) echo "usage : install-engine.sh cuda|cpu [choix.json]" >&2; exit 2 ;; esac
PYTHON_VERSION="3.12.12"  # the one used by the tests

HOME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/geonesclick/engine"
export UV_PYTHON_INSTALL_DIR="$HOME_DIR/python" UV_CACHE_DIR="$HOME_DIR/cache" UV_NO_CONFIG=1
NEW="$HOME_DIR/venv.new"
mkdir -p "$HOME_DIR"
rm -rf "$NEW"

echo "PHASE python"
"$B/uv" venv --quiet --python "$PYTHON_VERSION" --managed-python "$NEW"

echo "PHASE paquets"
if [ "$VARIANT" = cpu ]; then
  # PyTorch CPU comes from the PyTorch index; its hash is pinned in requirements-cpu.txt.
  "$B/uv" pip install --python "$NEW/bin/python" --require-hashes -r "$B/requirements-cpu.txt" \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
else
  "$B/uv" pip install --python "$NEW/bin/python" --require-hashes -r "$B/requirements-cuda.txt"
fi

echo "PHASE moteur"
"$B/uv" pip install --python "$NEW/bin/python" --no-deps "$B"/wheels/*.whl

# Your choices (options accepted or declined) are written BEFORE any start of the engine: it will never download
# an option you declined.
if [ -n "$CHOICES" ]; then
  echo "PHASE choix"
  "$NEW/bin/python" -m geonesclick.settings < "$CHOICES"
fi

echo "PHASE modele"
"$NEW/bin/python" -m geonesclick.fetch streetclip

echo "PHASE finition"
rm -rf "$HOME_DIR/venv"
mv "$NEW" "$HOME_DIR/venv"
cp "$B/VERSION" "$HOME_DIR/VERSION"
"$B/uv" cache clean --quiet || true  # the packages are installed: their cached copy is no longer needed
echo "PHASE fini"
