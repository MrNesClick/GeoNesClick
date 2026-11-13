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
# leaves a half-installed engine. An update starts venv.new from a copy of the installed engine when its Python is
# the same, then syncs it to the new requirements: only the libraries that changed are downloaded (a few MB when only
# GeoNesClick changed, instead of 3.1 GB with PyTorch CUDA); the copy needs the engine's size free for a moment.
# Output readable by the assistant: "PHASE <name>" lines.
set -eu

B="$(cd "$(dirname "$0")" && pwd)"
VARIANT="${1:-}"
CHOICES="${2:-}"
case "$VARIANT" in cuda|cpu) ;; *) echo "usage: install-engine.sh cuda|cpu [choices.json]" >&2; exit 2 ;; esac
PYTHON_VERSION="3.12.12"  # the one used by the tests

HOME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/geonesclick/engine"
# 5 retries per download instead of uv's 3: rides out a short outage of GitHub, PyPI or PyTorch (504s).
export UV_PYTHON_INSTALL_DIR="$HOME_DIR/python" UV_CACHE_DIR="$HOME_DIR/cache" UV_NO_CONFIG=1 UV_HTTP_RETRIES=5
NEW="$HOME_DIR/venv.new"
mkdir -p "$HOME_DIR"
rm -rf "$NEW"

OLD="$HOME_DIR/venv"
# The installed variant: written since 0.5.0; before, PyTorch's own version tells (2.9.1+cpu for the processor one).
installed_variant() {
  if [ -f "$HOME_DIR/VARIANT" ]; then cat "$HOME_DIR/VARIANT"; return; fi
  for torch in "$OLD"/lib/python3*/site-packages/torch-*.dist-info; do
    [ -d "$torch" ] || continue
    case "$torch" in *+cpu.dist-info) echo cpu ;; *) echo cuda ;; esac
    return
  done
}
echo "PHASE python"
if [ -x "$OLD/bin/python" ] && [ "$(installed_variant)" = "$VARIANT" ] \
   && [ "$("$OLD/bin/python" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)" = "$PYTHON_VERSION" ]; then
  cp -a "$OLD" "$NEW"  # an update: the libraries already installed are kept
else
  "$B/uv" venv --quiet --python "$PYTHON_VERSION" --managed-python "$NEW"
fi

echo "PHASE packages"
# sync, not install: the venv ends with exactly the pinned libraries, those an update no longer needs removed.
if [ "$VARIANT" = cpu ]; then
  # PyTorch CPU comes from the PyTorch index; its hash is pinned in requirements-cpu.txt.
  "$B/uv" pip sync --python "$NEW/bin/python" --require-hashes "$B/requirements-cpu.txt" \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
else
  "$B/uv" pip sync --python "$NEW/bin/python" --require-hashes "$B/requirements-cuda.txt"
fi

echo "PHASE engine"
# --reinstall: an update replaces the engine even when a rebuild kept its version number.
"$B/uv" pip install --python "$NEW/bin/python" --no-deps --reinstall "$B"/wheels/*.whl

# Your choices (options accepted or declined) are written BEFORE any start of the engine: it will never download
# an option you declined.
if [ -n "$CHOICES" ]; then
  echo "PHASE choices"
  "$NEW/bin/python" -m geonesclick.settings < "$CHOICES"
fi

echo "PHASE model"
"$NEW/bin/python" -m geonesclick.fetch streetclip

echo "PHASE finish"
rm -rf "$HOME_DIR/venv"
mv "$NEW" "$HOME_DIR/venv"
cp "$B/VERSION" "$HOME_DIR/INSTALLED"  # complete installation
echo "$VARIANT" > "$HOME_DIR/VARIANT"  # an update installs the same one, without asking
# The engine may start only once the choices are written (otherwise it would follow the defaults and download
# options the user declined): here if they were given, otherwise the assistant writes VERSION after applying them.
if [ -n "$CHOICES" ]; then cp "$B/VERSION" "$HOME_DIR/VERSION"; fi
"$B/uv" cache clean --quiet || true  # the packages are installed: their cached copy is no longer needed
echo "PHASE done"
