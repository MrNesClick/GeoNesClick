# GeoNesClick

Coach d'entraînement GeoGuessr assisté par IA. Il analyse ce que tu vois à l'écran et te guide, selon un
**niveau d'aide configurable**, vers les indices utiles : où regarder, ce qu'on y voit, ce que ça implique.

> **Usage visé : l'entraînement** (parties solo, cartes non classées). Le coach ne lit jamais les données
> du jeu, uniquement l'image affichée. Les règles de GeoGuessr interdisent les outils tiers en partie
> classée : ne l'utilise pas en compétition.

## État du projet

**Squelette de bout en bout** ✅ (2026-11-07) : raccourci → capture → niveau 1 en local → niveau 2 distant,
affichés dans la fenêtre du coach.

| Étape | Mesuré |
|---|---|
| Raccourci → capture | environ 0,3 s, notification GNOME avec miniature et son |
| Niveau 1 : StreetCLIP en local (RTX 3050 Ti) | environ 60 ms à chaud, 846 Mo de mémoire vidéo |
| Niveau 2 : Nemotron 3.5 Super VL (NVIDIA), sans raisonnement | de 3 à 15 s selon la charge du service |

À venir, dans l'ordre :
1. **Détection automatique de la vue Street View** (recadrage et masquage de l'interface du jeu).
   Sans elle, l'écran entier est analysé et le niveau 1 est faussé (« France » sur une rue de Hongrie).
2. **Base de metas** (Plonk It) pour le niveau 1 « où regarder pour départager ».
3. Banc d'essai des modèles de vision sur un jeu de test étiqueté.

Enseignements de la phase 0 (tests de faisabilité) :
- Sur le palier gratuit NVIDIA, la disponibilité varie : le 2026-11-07, `z-ai/glm-5.3-flash` et
  `meta/llama-3.2-90b-vision-instruct` ne répondaient pas ; Nemotron Nano Omni répondait en 5 s mais
  inventait des détails. D'où le choix de Nemotron 3.5 Super VL par défaut.
- Le partage d'écran peut être coupé depuis l'indicateur de GNOME : le coach le signale et propose
  « Relancer le partage ».
- Un `gsettings` tiers (Linuxbrew) peut ne pas écrire dans les réglages GNOME : le script appelle
  explicitement `/usr/bin/gsettings`.

## Prérequis

- Ubuntu 24.04 ou plus récent, avec GNOME (Wayland ou Xorg)
- Une carte NVIDIA avec CUDA (recommandé ; sans elle, StreetCLIP tourne sur CPU, plus lentement)
- [Rust](https://rustup.rs), [Node.js](https://nodejs.org) et [pnpm](https://pnpm.io), [uv](https://docs.astral.sh/uv/)
- Une clé API NVIDIA gratuite : [build.nvidia.com](https://build.nvidia.com)

Les paquets système (WebKitGTK pour Tauri, GStreamer et PipeWire pour la capture, en-têtes pour compiler
PyGObject) sont vérifiés par le script d'installation.

## Installation

```bash
scripts/install.sh                  # vérifie tout et installe les dépendances du projet
scripts/install.sh --with-apt       # installe aussi les paquets système manquants (demande sudo)
scripts/install.sh --setup-shortcut # ajoute le raccourci GNOME de capture (Super+Maj+G par défaut)
```

Le script peut être relancé sans risque, par exemple après chaque `git pull`. Ensuite, renseigne ta clé
dans `.env` (le script le crée à partir de `.env.example`) :

```
NVAPI=nvapi-...
```

Pour changer le raccourci : `GNC_SHORTCUT="<Super><Shift>h" scripts/install.sh --setup-shortcut`.

Le moteur utilise un **Python 3.12 géré par uv**, dans un environnement virtuel **isolé** des paquets
système. Les liaisons GStreamer (PyGObject) sont compilées depuis PyPI à l'installation, d'où les paquets
`libgirepository-2.0-dev` et `libcairo2-dev`. Seuls les fichiers de description GStreamer (`gir1.2-*`)
viennent du système.

## Lancer

```bash
cd app && pnpm tauri dev
```

La fenêtre du coach démarre le moteur Python et l'arrête à sa fermeture. La première fois, GNOME demande
quelle fenêtre partager : choisis la fenêtre du navigateur où tu joues. L'autorisation est mémorisée
dans `~/.config/geonesclick/screencast.token` ; supprime ce fichier pour choisir une autre fenêtre.

Pendant une manche, appuie sur **Super+Maj+G** (ou sur « Capturer »). Le coach affiche :
1. les **pays probables**, calculés en local et instantanément ;
2. **ce que voit l'IA**, quelques secondes plus tard, masqué derrière « Révéler les observations » au
   niveau d'aide 1 pour que tu cherches d'abord par toi-même.

Pour lancer le moteur seul (sans interface) : `cd engine && .venv/bin/python -m geonesclick`.

## Tests

```bash
cd engine && .venv/bin/python -m pytest -q
```

Ils couvrent la configuration (fusion, validation), le recadrage et les masques, la lecture de la réponse
du modèle de vision, et les règles d'accès du serveur (origines refusées en HTTP et WebSocket).

## Configuration

Tout se règle dans `~/.config/geonesclick/config.toml`, qui surcharge clé par clé les valeurs par
défaut commentées de [`engine/src/geonesclick/default_config.toml`](engine/src/geonesclick/default_config.toml).
Exemple :

```toml
[coach]
default_level = 2          # observations de l'IA affichées sans clic

[capture]
source = "window"               # "window" (défaut), "monitor" ou "both" : ce que GNOME propose de partager
sound = false
crop = [0.0, 0.13, 1.0, 0.98]   # zone analysée en fractions [gauche, haut, droite, bas]

[vision]
model = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
```

Relance l'application après une modification. La liste des modèles disponibles est publique :
`curl -s https://integrate.api.nvidia.com/v1/models`.

## Architecture

```
Raccourci GNOME ─► moteur Python (FastAPI, 127.0.0.1:47615) ◄─ WebSocket ─► fenêtre Tauri + Vue
                     │
                     ├─ capture : portail ScreenCast + PipeWire + GStreamer (flux continu)
                     ├─ niveau 1 : StreetCLIP local (pays probables)        [+ metas, à venir]
                     └─ niveau 2 : modèle de vision NVIDIA (fiche d'indices, asynchrone)
```

| Élément | Choix | Configurable |
|---|---|---|
| Interface | Tauri 2 + Vue 3 + Tailwind 4 | — |
| Moteur | Python 3.12, FastAPI + WebSocket | port, origines autorisées |
| Capture | Portail ScreenCast + PipeWire + GStreamer | recadrage, masques, notification, son |
| Niveau 1 | StreetCLIP (`geolocal/StreetCLIP`) | modèle, prompt, liste de pays, top N |
| Niveau 2 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | modèle, prompt, raisonnement, délai |
| Metas | Plonk It, mise à jour manuelle avec récapitulatif à valider (à venir) | — |

**Sécurité** : le moteur n'écoute que sur `127.0.0.1` et refuse toute origine web inconnue (un site
ouvert dans le navigateur ne peut ni déclencher de capture ni lire les résultats). Le socket du
raccourci est en `0600`. La clé API ne quitte que vers l'API NVIDIA.

## Arborescence

```
app/                      interface Tauri + Vue
  src-tauri/src/lib.rs    lance et arrête le moteur
  src/engine.ts           connexion au moteur (WebSocket + HTTP)
  src/components/         niveau 1 (Candidates), niveau 2 (Observations)
engine/                   moteur Python
  src/geonesclick/     capture, StreetCLIP, vision, serveur, configuration
  spikes/                 outils de mesure : StreetCLIP (streetclip_bench.py), modèle de vision (vlm_probe.py)
  captures/               captures d'écran (ignorées par git)
scripts/install.sh        installation
```
