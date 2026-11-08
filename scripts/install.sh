#!/usr/bin/env bash
# Installation of GeoNesClick (Ubuntu 24.04+ / GNOME / Wayland or Xorg).
#
# Usage:
#   scripts/install.sh                  checks the prerequisites and installs the project's dependencies
#   scripts/install.sh --with-apt       also installs the missing system packages (sudo apt)
#   scripts/install.sh --setup-shortcut adds the GNOME shortcuts: capture (default: Super+Shift+G,
#                                       can be changed with GNC_SHORTCUT="<Super><Shift>g") and marks
#                                       (default: Super+Shift+Z, can be changed with GNC_MARK_SHORTCUT)
#
# The script is idempotent: it can safely be run again after each update of the repository.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_APT=0
SETUP_SHORTCUT=0
for arg in "$@"; do
  case "$arg" in
    --with-apt) WITH_APT=1 ;;
    --setup-shortcut) SETUP_SHORTCUT=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ---------------------------------------------------------------------------
step "1. System packages"
APT_PACKAGES=(
  # Tauri 2: https://v2.tauri.app/start/prerequisites/#linux
  build-essential curl wget file libxdo-dev libssl-dev
  libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev
  # Compiling PyGObject (GStreamer bindings) in the venv: https://pygobject.gnome.org/getting_started.html
  pkg-config libcairo2-dev libgirepository-2.0-dev
  # Capture: GStreamer descriptions (typelibs), video conversion, PipeWire source, ScreenCast portal
  gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-base gstreamer1.0-pipewire
  xdg-desktop-portal xdg-desktop-portal-gnome
)
MISSING=()
for pkg in "${APT_PACKAGES[@]}"; do
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || MISSING+=("$pkg")
done
if ((${#MISSING[@]} == 0)); then
  ok "all system packages are present"
elif ((WITH_APT)); then
  warn "installing: ${MISSING[*]}"
  sudo apt-get update && sudo apt-get install -y "${MISSING[@]}"
else
  fail "missing packages: ${MISSING[*]}"
  echo "     → run again with --with-apt, or: sudo apt install ${MISSING[*]}"
  exit 1
fi

# ---------------------------------------------------------------------------
step "2. Development tools"
need_tool() {  # name, version command, installation help
  if command -v "$1" >/dev/null 2>&1; then ok "$1 $($2 2>/dev/null | head -1)"; else fail "$1 missing → $3"; return 1; fi
}
TOOLS_OK=1
need_tool cargo "cargo --version" "https://rustup.rs" || TOOLS_OK=0
need_tool node "node --version" "https://nodejs.org (LTS) or nvm" || TOOLS_OK=0
need_tool pnpm "pnpm --version" "corepack enable pnpm, or https://pnpm.io/installation" || TOOLS_OK=0
need_tool uv "uv --version" "curl -LsSf https://astral.sh/uv/install.sh | sh" || TOOLS_OK=0
((TOOLS_OK)) || exit 1

# ---------------------------------------------------------------------------
step "3. Python engine (engine/)"
# Isolated venv: Python 3.12 managed by uv, no system package visible. PyGObject is compiled from
# PyPI; only the GStreamer typelibs (description files) come from the system.
cd "$ROOT/engine"
if [[ -f .venv/pyvenv.cfg ]] && grep -q "include-system-site-packages = true" .venv/pyvenv.cfg; then
  warn "old non-isolated venv detected: recreating it"
  rm -rf .venv
fi
uv sync --managed-python
ok "isolated venv up to date"
.venv/bin/python -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst" \
  && ok "GStreamer bindings available" || { fail "GStreamer bindings not found in the venv"; exit 1; }
.venv/bin/python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" \
  && ok "PyTorch sees the GPU" || warn "PyTorch sees no CUDA GPU: StreetCLIP will run on the CPU (slow)"

# Places directory (GeoNames, CC BY 4.0, ~11 MB) for the marks' rules; otherwise, the coach
# downloads it on its first start. A failure (offline) does not prevent the installation.
if [[ -f "${XDG_DATA_HOME:-$HOME/.local/share}/geonesclick/places/places-v4.sqlite" ]]; then
  ok "GeoNames places directory present"
else
  .venv/bin/python -m geonesclick.places && ok "GeoNames places directory built" \
    || warn "places directory not downloaded: the coach will retry when it starts"
fi

# ---------------------------------------------------------------------------
step "4. Tauri app (app/)"
cd "$ROOT/app"
pnpm install --frozen-lockfile
ok "front-end dependencies installed"

# ---------------------------------------------------------------------------
step "5. Configuration"
cd "$ROOT"
# API key: entered in the app (Settings › Analysis), stored in ~/.config/geonesclick/nvapi.key (0600), never
# in the repository. A key left in the old .env is moved there on the engine's first start.
KEY_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/geonesclick/nvapi.key"
if [[ -n "${NVAPI:-}" ]]; then
  ok "API key provided by the NVAPI variable"
elif [[ -s "$KEY_FILE" ]]; then
  ok "API key saved ($KEY_FILE)"
elif [[ -f .env ]] && grep -q '^NVAPI=.\+' .env; then
  ok "API key in the old .env: it will be moved on first start"
else
  warn "no API key yet: enter it in the app, Settings › Analysis (Réglages › Analyse, https://build.nvidia.com)"
fi

# ---------------------------------------------------------------------------
if ((SETUP_SHORTCUT)); then
  step "6. GNOME shortcuts"
  # Always the system's gsettings: a third-party gsettings (Linuxbrew, conda…) may lack the
  # dconf module and write to a file that GNOME never reads.
  gsettings() { /usr/bin/gsettings "$@"; }
  SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
  add_shortcut() {  # identifier, name, trigger command, key combination
    local key_path="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/$1/" current new
    current="$(gsettings get "$SCHEMA" custom-keybindings)"
    if [[ "$current" != *"$key_path"* ]]; then
      if [[ "$current" == "@as []" || "$current" == "[]" ]]; then new="['$key_path']"; else new="${current%]}, '$key_path']"; fi
      gsettings set "$SCHEMA" custom-keybindings "$new"
    fi
    local rel="$SCHEMA.custom-keybinding:$key_path"
    gsettings set "$rel" name "$2"
    gsettings set "$rel" command "$ROOT/engine/.venv/bin/python -m geonesclick.trigger $3"
    gsettings set "$rel" binding "$4"
    ok "shortcut $4 → $3"
  }
  add_shortcut geonesclick "GeoNesClick – capture" capture "${GNC_SHORTCUT:-<Super><Shift>g}"
  add_shortcut geonesclick-mark "GeoNesClick – marques" mark "${GNC_MARK_SHORTCUT:-<Super><Shift>z}"
fi

step "Installation done ✔  (see README.md, section \"Install and run\")"
