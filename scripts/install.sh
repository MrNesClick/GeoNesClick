#!/usr/bin/env bash
# Installation de GeoNesClick (Ubuntu 24.04+ / GNOME / Wayland ou Xorg).
#
# Usage :
#   scripts/install.sh                  vérifie les prérequis et installe les dépendances du projet
#   scripts/install.sh --with-apt       installe aussi les paquets système manquants (sudo apt)
#   scripts/install.sh --setup-shortcut ajoute les raccourcis GNOME : capture (défaut : Super+Maj+G,
#                                       modifiable avec GNC_SHORTCUT="<Super><Shift>g") et marques
#                                       (défaut : Super+Maj+Z, modifiable avec GNC_MARK_SHORTCUT)
#
# Le script est idempotent : on peut le relancer sans risque après chaque mise à jour du dépôt.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_APT=0
SETUP_SHORTCUT=0
for arg in "$@"; do
  case "$arg" in
    --with-apt) WITH_APT=1 ;;
    --setup-shortcut) SETUP_SHORTCUT=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $arg" >&2; exit 2 ;;
  esac
done

ok()   { printf '  \033[32m✔\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# ---------------------------------------------------------------------------
step "1. Paquets système"
APT_PACKAGES=(
  # Tauri 2 : https://v2.tauri.app/start/prerequisites/#linux
  build-essential curl wget file libxdo-dev libssl-dev
  libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev
  # Compilation de PyGObject (liaisons GStreamer) dans le venv : https://pygobject.gnome.org/getting_started.html
  pkg-config libcairo2-dev libgirepository-2.0-dev
  # Capture : descriptions GStreamer (typelibs), conversion vidéo, source PipeWire, portail ScreenCast
  gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-base gstreamer1.0-pipewire
  xdg-desktop-portal xdg-desktop-portal-gnome
)
MISSING=()
for pkg in "${APT_PACKAGES[@]}"; do
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || MISSING+=("$pkg")
done
if ((${#MISSING[@]} == 0)); then
  ok "tous les paquets système sont présents"
elif ((WITH_APT)); then
  warn "installation de : ${MISSING[*]}"
  sudo apt-get update && sudo apt-get install -y "${MISSING[@]}"
else
  fail "paquets manquants : ${MISSING[*]}"
  echo "     → relance avec --with-apt, ou : sudo apt install ${MISSING[*]}"
  exit 1
fi

# ---------------------------------------------------------------------------
step "2. Outils de développement"
need_tool() {  # nom, commande de version, aide d'installation
  if command -v "$1" >/dev/null 2>&1; then ok "$1 $($2 2>/dev/null | head -1)"; else fail "$1 absent → $3"; return 1; fi
}
TOOLS_OK=1
need_tool cargo "cargo --version" "https://rustup.rs" || TOOLS_OK=0
need_tool node "node --version" "https://nodejs.org (LTS) ou nvm" || TOOLS_OK=0
need_tool pnpm "pnpm --version" "corepack enable pnpm, ou https://pnpm.io/installation" || TOOLS_OK=0
need_tool uv "uv --version" "curl -LsSf https://astral.sh/uv/install.sh | sh" || TOOLS_OK=0
((TOOLS_OK)) || exit 1

# ---------------------------------------------------------------------------
step "3. Moteur Python (engine/)"
# Venv isolé : Python 3.12 géré par uv, aucun paquet système visible. PyGObject est compilé depuis
# PyPI ; seuls les typelibs GStreamer (fichiers de description) viennent du système.
cd "$ROOT/engine"
if [[ -f .venv/pyvenv.cfg ]] && grep -q "include-system-site-packages = true" .venv/pyvenv.cfg; then
  warn "ancien venv non isolé détecté : recréation"
  rm -rf .venv
fi
uv sync --managed-python
ok "venv isolé à jour"
.venv/bin/python -c "import gi; gi.require_version('Gst', '1.0'); from gi.repository import Gst" \
  && ok "liaisons GStreamer accessibles" || { fail "liaisons GStreamer introuvables dans le venv"; exit 1; }
.venv/bin/python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" \
  && ok "PyTorch voit le GPU" || warn "PyTorch ne voit pas de GPU CUDA : StreetCLIP tournera sur CPU (lent)"

# Répertoire des lieux (GeoNames, CC BY 4.0, ~11 Mo) pour les règles des marques ; sinon, le coach le
# télécharge à son premier démarrage. Un échec (hors ligne) n'empêche pas l'installation.
if [[ -f "${XDG_DATA_HOME:-$HOME/.local/share}/geonesclick/places/places-v4.sqlite" ]]; then
  ok "répertoire des lieux GeoNames présent"
else
  .venv/bin/python -m geonesclick.places && ok "répertoire des lieux GeoNames construit" \
    || warn "répertoire des lieux non téléchargé : le coach réessaiera à son démarrage"
fi

# ---------------------------------------------------------------------------
step "4. Application Tauri (app/)"
cd "$ROOT/app"
pnpm install --frozen-lockfile
ok "dépendances front installées"

# ---------------------------------------------------------------------------
step "5. Configuration"
cd "$ROOT"
if [[ -f .env ]]; then
  grep -q '^NVAPI=.\+' .env && ok ".env présent avec NVAPI" || warn ".env présent mais NVAPI vide"
else
  cp .env.example .env && chmod 600 .env
  warn ".env créé depuis .env.example : renseigne ta clé NVAPI (https://build.nvidia.com)"
fi

# ---------------------------------------------------------------------------
if ((SETUP_SHORTCUT)); then
  step "6. Raccourcis GNOME"
  # Toujours le gsettings du système : un gsettings tiers (Linuxbrew, conda…) peut ne pas avoir le
  # module dconf et écrire dans un fichier que GNOME ne lit jamais.
  gsettings() { /usr/bin/gsettings "$@"; }
  SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
  add_shortcut() {  # identifiant, nom, commande du déclencheur, combinaison
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
    ok "raccourci $4 → $3"
  }
  add_shortcut geonesclick "GeoNesClick – capture" capture "${GNC_SHORTCUT:-<Super><Shift>g}"
  add_shortcut geonesclick-mark "GeoNesClick – marques" mark "${GNC_MARK_SHORTCUT:-<Super><Shift>z}"
fi

step "Installation terminée ✔  (voir README.md, section « Lancer »)"
