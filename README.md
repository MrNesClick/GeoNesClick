# GeoNesClick

Coach d'entraînement GeoGuessr assisté par IA. Il analyse ce que tu vois à l'écran et te guide, selon un
**niveau d'aide configurable**, vers les indices utiles : où regarder, ce qu'on y voit, ce que ça implique.

> **Mode de jeu conseillé : la partie classique** (une carte, 5 manches). C'est le seul mode dont
> l'interface est prise en charge pour l'instant ; les autres (défis, streaks…) pourront suivre.
>
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
| Niveau 2 : Nemotron 3.5 Super VL (NVIDIA), sans raisonnement | de 3 à 5 s en général, jusqu'à 15 s selon la charge |

Fonctionnalités :
- **Niveau 1 « Où regarder »**, sans spoiler : le coach montre d'abord les catégories d'indices qui
  départagent les pays probables et quoi y observer (« Regarde la couleur de la ligne centrale. »),
  puis, sur demande, les pays et l'indice propre à chacun.
- **Vérifier l'amorce en jouant** : « Juste » / « Faux » sur chaque indice non vérifié.
- **Niveau 2 « Ce que voit l'IA »**, révélable : la fiche d'indices du modèle de vision.
- **« C'était où ? »** après la manche : tu donnes le pays réel et celui que tu avais répondu ; la
  capture rejoint le jeu de test, et le coach suit ta progression (pays trouvés, pays à retravailler,
  justesse de StreetCLIP) et **tes confusions**, avec les metas qui séparent les deux pays.
- **Réglages** dans l'application, appliqués à chaud, avec la liste des modèles NVIDIA et un bouton
  « Tester ce modèle » (vérifie qu'il accepte les images et mesure sa latence).
- **Changer de fenêtre** partagée à tout moment.

À venir, dans l'ordre :
1. Agrandir le jeu de test (20 à 30 captures via « C'était où ? », avec des vues urbaines pour le texte).
2. Mesurer le texte visible (transcription par le niveau 2, domaines, indicatifs) et les questions fermées.
3. Détection automatique de la vue Street View : **reportée**, voir ci-dessous.

Moyenner StreetCLIP sur plusieurs recadrages (image entière, gauche, centre, droite) aide-t-il ?
Mesuré sur les mêmes 5 captures (`spikes/streetclip_tta.py`) : non. Top-1 inchangé (3/5), probabilité
moyenne du bon pays en baisse (49 % → 41 %) ; les recadrages partiels donnent plus de poids à la barre
du navigateur. Non retenu.

Recadrer et masquer l'interface du jeu valent-ils la peine ? Mesuré le 2026-11-07 sur 5 captures de
partie classique (`spikes/compare_views.py`) :

| Variante | Bon pays 1ᵉʳ | Dans le top 3 | Probabilité moyenne | Noms de pays recopiés par l'IA |
|---|---|---|---|---|
| Fenêtre du navigateur entière | 3/5 | 4/5 | 49 % | 0/5 |
| Vue recadrée | 2/5 | 4/5 | 47 % | 0/5 |
| Vue recadrée et interface masquée | 2/5 | 4/5 | 44 % | 0/5 |

Capturer la **fenêtre** (et non l'écran) suffit : aucun gain mesurable du recadrage, et les masques noirs
semblent même gêner StreetCLIP. Le recadrage et les masques restent disponibles en configuration ; on
remesurera avec un jeu de test plus grand.

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
(`~/.config/geonesclick/screencast.token`). Pour en changer (autre navigateur, écran ou résolution),
clique sur **Changer de fenêtre** en bas du coach : le sélecteur de GNOME se rouvre.

Pendant une manche, appuie sur **Super+Maj+G** (ou sur « Capturer »). Le coach affiche :
1. les **pays probables**, calculés en local et instantanément ;
2. **ce que voit l'IA**, quelques secondes plus tard, masqué derrière « Révéler les observations » au
   niveau d'aide 1 pour que tu cherches d'abord par toi-même.

Pour lancer le moteur seul (sans interface) : `cd engine && .venv/bin/python -m geonesclick`.

## Tests

```bash
cd engine && .venv/bin/python -m pytest -q
```

Ils couvrent la configuration, le recadrage et les masques, la réponse du modèle de vision, les metas et
le départage, le jeu de test et la progression, les réglages (liste blanche, écriture atomique), et les
règles d'accès du serveur (origines, Host, pré-vérification CORS, traversée de chemin).

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

Chaque aide se désactive : niveau 2, amorce, consignes « Regarde… », boutons « Juste » / « Faux », pays
répondu, confusions, notifications, copie des captures (sections `[coach]`, `[vision]`, `[metas]`,
`[dataset]`, `[capture]` du fichier par défaut).
Pour retirer des pays candidats : `[streetclip] exclude_countries = ["RU", "UA"]` (ton fichier peut
ajouter des pays à la liste, mais pas en enlever autrement).

L'écran **Réglages** de l'application modifie les réglages courants à chaud : il n'écrit dans ce fichier
que les valeurs que tu changes, en conservant tes commentaires et leur ordre. L'adresse de l'API, la clé, le port, les origines, le recadrage, les prompts, les consignes et les
poids des catégories (`category_looks`, `category_weights`) ne se modifient que dans le fichier, puis
en relançant l'application. La liste des modèles est publique :
`curl -s https://integrate.api.nvidia.com/v1/models`.

## Metas

Une meta est un indice visuel attaché à un ou plusieurs pays. Le niveau 1 choisit les **catégories qui
séparent le mieux les pays probables**, pondérées par leurs probabilités : une catégorie qui distingue
les deux favoris passe avant une qui distingue deux outsiders.

Sources, de la plus prioritaire à la moins prioritaire :
1. **Tes metas** : `~/.config/geonesclick/mes-metas.toml`, affichées « (ta meta) » ;
2. **L'amorce** : une cinquantaine de faits très établis (alphabets, sens de circulation, couleur de la
   ligne centrale, domaines), rédigée sans source vérifiée, affichée « (amorce, à vérifier) ».

Format (catégories : `langue`, `conduite`, `marquage`, `poteaux`, `bornes`, `plaques`, `panneaux`,
`domaine`, `voiture`, `vegetation`, `architecture`, `autre`) :

```toml
[[meta]]
category = "poteaux"
countries = ["HU"]
hint = "Poteaux en béton percés de trous"
look = "les trous dans les poteaux"   # facultatif : la consigne sans spoiler
verified = true
```

Avant de révéler les pays, le coach affiche pour chaque catégorie **quoi observer** (« Regarde la couleur
de la ligne centrale. »), sans nommer de pays : c'est le champ `look` des metas, ou à défaut une consigne
propre à la catégorie.

Une erreur dans ce fichier est signalée dans l'écran Réglages, sans bloquer le coach.

**Vérifier l'amorce en jouant.** Chaque indice de l'amorce affiché porte deux boutons : **Juste** en
ajoute une copie vérifiée à `mes-metas.toml` (elle devient « ta meta, vérifiée »), **Faux** l'écarte
(bloc `[[rejected]]`, avec la catégorie et le texte de l'indice). Les verdicts sont ajoutés en fin de
fichier, sans toucher au reste : tes commentaires sont conservés. Pour annuler, supprime le bloc.

### Guides Plonk It

Le coach collecte les guides de [Plonk It](https://www.plonkit.net) **sur ta machine, pour ton usage** :
la base n'est jamais redistribuée ni versionnée, chaque installation construit la sienne. Collecte polie :
une page à la fois, 2 s de pause (plus un délai aléatoire), arrêt immédiat si le site répond 429, et la
voie qu'indique Plonk It lui-même (le bloc `__PRELOADED_DATA__` des pages ; leur API ne sert que le guide
débutant). Le `robots.txt` du site autorise l'accès (`Allow: /`) et n'interdit que l'entraînement d'IA,
ce que le coach ne fait pas.

- **Premier démarrage** : construction en arrière-plan (~3 min pour 84 pays, environ 4 000 astuces) ; le
  coach fonctionne sans en attendant.
- **Ensuite** : une requête sur la liste des guides au plus tous les `refresh_days` jours (30 par défaut),
  et seuls les guides modifiés sont rechargés. Bouton « Mettre à jour maintenant » dans les Réglages.
- **Stockage** : `~/.local/share/geonesclick/plonkit/` (pages brutes + `plonkit.sqlite` : astuces,
  recherche plein texte FTS5, vecteurs CLIP en cache).
- **Au niveau 1**, quand les pays sont révélés : pour chaque candidat, les astuces Plonk It classées par
  ressemblance avec l'image, avec un lien vers le guide. C'est **une piste à vérifier** : la comparaison
  capte l'allure générale de la vue, pas forcément un élément précis (voir les mesures ci-dessous).
- Chaque astuce est rangée dans une catégorie de metas par ses étiquettes Plonk It, puis par mots-clés
  (`[plonkit] keywords`) ; environ 25 % restent « autres » pour l'instant.

Commande manuelle : `cd engine && .venv/bin/python -m geonesclick.plonkit collect`.

**Quel moteur de recherche ?** Mesuré sur les 4 060 astuces (`spikes/search_bench.py`) : un dictionnaire
en mémoire, SQLite FTS5 et Tantivy répondent tous en moins d'une milliseconde (StreetCLIP : 60 ms) ;
Elasticsearch ou Meilisearch n'apporteraient qu'un serveur de plus. Retrouver le pays en cherchant le
texte de la fiche du niveau 2 dans les astuces échoue avec tous les moteurs (rang moyen ~50ᵉ sur 84) ;
comparer l'image aux astuces (vecteurs CLIP) classe le bon pays 1ᵉʳ ou 2ᵉ 4 fois sur 5, mais n'améliore
pas StreetCLIP une fois fusionné (même modèle, signal redondant). D'où SQLite + vecteurs, sans moteur dédié.

Limite constatée : si StreetCLIP classe le bon pays trop bas (la Serbie à 3 %, sous le seuil de 5 %),
aucune meta ne peut le rattraper. Les prochains leviers sont indépendants de StreetCLIP : le texte visible
et des questions fermées posées au niveau 2.

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
| Metas | tes metas, amorce, guides Plonk It collectés en local (SQLite + vecteurs CLIP) | activation, rafraîchissement, mots-clés, nombre d'astuces |

**Sécurité** : le moteur n'écoute que sur `127.0.0.1` et refuse toute origine web inconnue (un site
ouvert dans le navigateur ne peut ni déclencher de capture ni lire les résultats). Le socket du
raccourci est en `0600`. La clé API ne quitte que vers l'API NVIDIA.

## Arborescence

```
app/                      interface Tauri + Vue
  src-tauri/src/lib.rs    lance et arrête le moteur
  src/engine.ts           connexion au moteur (WebSocket + HTTP)
  src/components/         niveau 1 (Candidates), niveau 2 (Observations), « C'était où ? »
                          (LabelForm), réglages (SettingsPanel)
engine/                   moteur Python
  src/geonesclick/     capture, StreetCLIP, vision, metas (+ amorce), jeu de test, réglages, serveur
  spikes/                 outils de mesure : StreetCLIP, modèle de vision, recadrage, multi-recadrage
  dataset/labels.toml     jeu de test étiqueté (images locales dans dataset/images/, non versionnées)
  captures/               captures d'écran (ignorées par git)
scripts/install.sh        installation
```
