#!/bin/sh
# Installe (ou met à jour) le moteur de GeoNesClick depuis l'AppImage : livré dans engine-bundle/ et lancé par
# l'assistant de premier lancement, APRÈS ton accord sur la liste des téléchargements (downloads.toml).
# Peut aussi se lancer à la main, sans interface (tests en conteneur) :
#
#   install-engine.sh cuda|cpu [choix.json]
#
# Tout va dans ~/.local/share/geonesclick/engine/ (Python, cache, venv) : rien n'est installé dans le système, et
# « Tout effacer » peut tout retirer d'un coup. Les dépendances sont vérifiées par empreinte (--require-hashes).
# Le moteur est d'abord installé à côté (venv.new) puis mis en place d'un coup : une installation interrompue ne
# laisse jamais un moteur à moitié installé. Sortie lisible par l'assistant : lignes « PHASE <nom> ».
set -eu

B="$(cd "$(dirname "$0")" && pwd)"
VARIANT="${1:-}"
CHOICES="${2:-}"
case "$VARIANT" in cuda|cpu) ;; *) echo "usage : install-engine.sh cuda|cpu [choix.json]" >&2; exit 2 ;; esac
PYTHON_VERSION="3.12.12"  # celle des tests

HOME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/geonesclick/engine"
export UV_PYTHON_INSTALL_DIR="$HOME_DIR/python" UV_CACHE_DIR="$HOME_DIR/cache" UV_NO_CONFIG=1
NEW="$HOME_DIR/venv.new"
mkdir -p "$HOME_DIR"
rm -rf "$NEW"

echo "PHASE python"
"$B/uv" venv --quiet --python "$PYTHON_VERSION" --managed-python "$NEW"

echo "PHASE paquets"
if [ "$VARIANT" = cpu ]; then
  # PyTorch CPU vient de l'index PyTorch ; son empreinte est figée dans requirements-cpu.txt.
  "$B/uv" pip install --python "$NEW/bin/python" --require-hashes -r "$B/requirements-cpu.txt" \
    --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
else
  "$B/uv" pip install --python "$NEW/bin/python" --require-hashes -r "$B/requirements-cuda.txt"
fi

echo "PHASE moteur"
"$B/uv" pip install --python "$NEW/bin/python" --no-deps "$B"/wheels/*.whl

# Tes choix (options acceptées ou refusées) sont écrits AVANT tout démarrage du moteur : il ne téléchargera jamais
# une option que tu as refusée.
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
"$B/uv" cache clean --quiet || true  # les paquets sont installés : leur copie en cache ne sert plus
echo "PHASE fini"
