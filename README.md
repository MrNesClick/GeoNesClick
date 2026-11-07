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
| Carte : nuage PLONK en local, en arrière-plan | environ 0,8 s pour 512 points, 119 Mo de mémoire vidéo en plus |

Fonctionnalités :
- **Quatre niveaux d'aide**, affichés sans clic et réglables en pleine partie : où regarder (« Regarde
  la couleur de la ligne centrale. »), ce que voit l'IA, les pays probables, la réponse avec sa preuve.
- **Vérifier l'amorce en jouant** : « Juste » / « Faux » sur chaque indice non vérifié.
- **Ce que voit l'IA** : la fiche d'indices du modèle de vision, dont le texte lu mot pour mot.
- **« C'était où ? »** après la manche : tu donnes le pays réel et celui que tu avais répondu ; la
  capture rejoint le jeu de test, et le coach suit ta progression (pays trouvés, pays à retravailler,
  justesse de StreetCLIP) et **tes confusions**, avec les metas qui séparent les deux pays.
- **Réglages** dans l'application, appliqués à chaud, avec la liste des modèles NVIDIA et un bouton
  « Tester ce modèle » (vérifie qu'il accepte les images et mesure sa latence).
- **Changer de fenêtre** partagée à tout moment.
- **Onglet Carte** (niveau 3 et plus) : pays probables colorés, pays écartés grisés par une preuve, et les
  **zones probables** délimitées à partir des positions calculées en local par PLONK, avec leur taille et
  leurs pays ; au niveau 4, une preuve forte recadre sur son pays.

À venir, dans l'ordre :
1. Agrandir le jeu de test (20 à 30 captures via « C'était où ? », avec des vues urbaines pour le texte).
2. Mesurer le texte visible (transcription par le niveau 2, domaines, indicatifs) et les questions fermées.
3. Détection automatique de la vue Street View : **reportée**, voir ci-dessous.
4. Carte : contour de la région lue par l'IA (contours des régions Natural Earth, noms en plusieurs langues),
   et le lieu exact cliqué sur la carte dans « C'était où ? » pour mesurer les écarts en km.

Moyenner StreetCLIP sur plusieurs recadrages (image entière, gauche, centre, droite) aide-t-il ?
Mesuré sur les mêmes 5 captures (`spikes/streetclip_tta.py`) : non. Top-1 inchangé (3/5), probabilité
moyenne du bon pays en baisse (49 % → 41 %) ; les recadrages partiels donnent plus de poids à la barre
du navigateur. Non retenu.

**PLONK peut-il placer la vue sur une carte ?** [PLONK](https://github.com/nicolas-dufour/plonk) (CVPR 2025,
MIT) tire un nuage de points GPS à partir du vecteur de StreetCLIP. Mesuré le 2026-11-07 sur les 5 captures
(`spikes/plonk_bench.py`, 512 points) ; l'écart est estimé depuis la zone notée dans le jeu de test :

| Réel | StreetCLIP 1ᵉʳ | PLONK 1ᵉʳ (pays où tombent le plus de points) | Centre du nuage | Écart estimé |
|---|---|---|---|---|
| Lettonie, côte ouest de Riga | Estonie (Lettonie 2ᵉ) | Pologne (Lettonie 7ᵉ) | région de Kaliningrad | ~340 km |
| Serbie, près de la Bulgarie | Croatie (Serbie 5ᵉ) | Croatie (Serbie 11ᵉ) | Autriche, vers Graz | ~700 km |
| Suède, vers Göteborg | Suède | Suède | vers Trollhättan | ~90 km |
| Norvège, nord d'Ålesund | Norvège | Norvège | sud de la Norvège | ~290 km |
| Lituanie, près de Vilnius | Lituanie | Lituanie | nord-est de la Pologne | ~190 km |

- **Pour choisir le pays, il n'apporte rien** : top-1 3/5 comme StreetCLIP, top-3 3/5 contre 4/5. Il lit
  le même vecteur que StreetCLIP, donc il en reprend les erreurs (même constat qu'avec les astuces Plonk It).
- **Pour la carte, il apporte ce que StreetCLIP ne donne pas** : une position dans le pays, à 90 à 300 km
  du lieu réel quand le pays est juste, et une dispersion qui dit si la vue est localisable (96 km pour la
  Norvège à 99 %, 270 km pour la Lettonie mal classée).
- **Coût** : 119 Mo de mémoire vidéo en plus (pic à 987 Mo avec StreetCLIP) ; aucune passe d'image en plus
  (même jeton `[CLS]` que StreetCLIP, cosinus 0,99998 entre notre fp16 et le fp32 d'entraînement) ; 3,8 s
  pour 512 points en 250 pas, 0,75 s en 50 pas.
- Jusqu'à 16 % des points tombent en mer (côtes, frontières au 1:50m).
- **Combien de pas ?** Même tirage de départ, 512 points :

  | Pas | Temps | Écart moyen du centre du nuage à celui à 250 pas | Pays |
  |---|---|---|---|
  | 250 (défaut du papier) | 3,8 s | — | top-1 3/5 |
  | 100 | 1,5 s | 28 km | identiques |
  | **50 (retenu)** | **0,75 s** | **20 km** | identiques |
  | 25 | 0,37 s | 35 km ; nuage norvégien élargi de 96 à 136 km | identiques |

  Jusqu'à 50 pas, l'écart est du bruit de tirage, négligeable devant l'erreur au lieu réel (90 à 300 km) ;
  à 25 pas, le nuage commence à se dégrader. Le temps suit le nombre de pas plus que le nombre de points :
  128 points à 50 pas prennent 0,28 s.

D'où la décision : **PLONK sert à la carte, pas au choix du pays**. Nuage calculé en arrière-plan après
StreetCLIP (50 pas, 512 points par défaut), filtré par la preuve, désactivable. Le moteur embarque une
version réduite du code PLONK (voir « Carte » ci-dessous), vérifiée identique au banc : mêmes points, même
centre de nuage, à 50 comme à 250 pas.

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
- Rallonger le prompt du modèle de vision dégrade sa lecture du texte : sur la plaque « Repkény utca », 8
  lectures exactes sur 10 avec le prompt actuel, 4 sur 12 avec des consignes en plus (ignorer l'interface du
  jeu, écrire « illisible »). Le texte de l'interface sera donc filtré par le coach, pas par le prompt.
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
ouvre l'onglet **Réglages** et clique sur **Changer de fenêtre** (section Captures) : le sélecteur de GNOME
se rouvre.

Pendant une manche, appuie sur **Super+Maj+G** (ou sur « Capturer »). Le coach affiche **tout seul,
sans clic**, l'aide du niveau choisi en haut de sa fenêtre :

| Niveau | Ce qui s'affiche |
|---|---|
| 1. Regarder | où regarder (catégories d'indices et quoi y observer), sans nommer de pays |
| 2. Indices | + ce que voit l'IA, dont le texte lu mot pour mot |
| 3. Pays | + pays probables, onglet Carte avec les zones probables, indices de chacun, astuces Plonk It traduites |
| 4. Réponse (défaut) | + synthèse en tête : pays, région si un texte la nomme, et la preuve |

Au niveau 4, la carte Réponse dit honnêtement ce que le coach sait :
- **une lecture de l'IA** (texte nommant un lieu, domaine, plaque…) passe en tête comme **« très probable :
  lu par l'IA, à confirmer »**, avec ce qu'elle a lu ; les autres pays restent affichés. Mesuré le 2026-11-07
  sur une plaque « Repkény utca » (Budapest) : sur 8 appels, le modèle a conclu 2 fois à tort avec « certitude
  forte » (Tchéquie sans avoir lu la plaque, Slovaquie en lisant « ulica »). Une conclusion ne deviendra
  **« certaine »** (pays en tête, autres écartés, `[coach] trust_proof`) qu'une fois confirmée par une règle
  locale (mot propre à une langue, domaine, indicatif) : c'est la prochaine étape ;
- **sans lecture**, un pays n'est donné que s'il **se détache** de l'allure de la vue (StreetCLIP) : au moins
  40 % et 15 points d'avance sur le 2ᵉ (`[coach] leader_min`, `leader_margin`). Sinon : **« Hésitation »**
  entre les premiers (ex. Bulgarie 22 %, Hongrie 21 %, Slovaquie 16 %, Roumanie 14 %), sans faux gagnant ;
- si l'IA signale un **texte illisible**, le coach conseille de zoomer dessus dans le jeu puis de recapturer :
  sur une capture roumaine, le panneau « Monumentul Eroilor Neamului » était illisible dans la vue entière, et
  lu exactement (Roumanie) une fois la zone découpée et agrandie trois fois. D'où la capture de zone, à venir.

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
help_level = 2             # où regarder + ce que voit l'IA, sans nommer de pays

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
Pour retirer des pays candidats : décoche-les dans Réglages › Analyse, ou `[streetclip] exclude_countries =
["RU", "UA"]` dans le fichier (il peut ajouter des pays à la liste, mais pas en enlever autrement).

**Tout est configurable**, aussi depuis l'onglet **Réglages** de l'application, rangé en sections repliables
(Aide, Analyse, Indices, Carte, Capture, Jeu de test, Moteur), chacune avec son résumé d'une ligne ; les
réglages fins sont dans une partie « Avancé ». Chaque changement s'applique et s'enregistre tout de suite (une
case, un menu, ou un champ à la sortie du champ) ; une valeur refusée est signalée sur place et l'écran revient
à la valeur en vigueur. L'écran n'écrit dans `config.toml` que les valeurs que tu changes, en conservant tes
commentaires et leur ordre. Pays candidats : décoche un pays pour l'écarter, ou ajoute-en un (nom anglais et
code ISO). Deux réglages ne prennent effet qu'au prochain démarrage (StreetCLIP activé et son calcul, ce que
GNOME propose de partager) : l'écran le signale.

**Seule exception, la sécurité** : ces réglages ne se changent que dans le fichier, puis en relançant
l'application. L'écran les affiche en lecture seule avec leur raison :

| Réglage | Pourquoi dans le fichier seulement |
|---|---|
| `[server]` host, port, allowed_origins | le moteur ne doit écouter que ta machine et ta fenêtre du coach |
| `[vision]` base_url, api_key_env | une requête pourrait rediriger ta clé API vers un autre serveur |
| `[streetclip]` model, `[plonk]` model, revision | un modèle téléchargé est exécuté sur ta machine : un modèle piégé pourrait exécuter du code |
| `[map]` tile_url, attribution_url | doivent aussi être autorisés dans la fenêtre (CSP et autorisations de Tauri) |
| dossiers et fichiers (`directory`, `user_file`, `data_dir`) | une requête ne doit pas pouvoir faire écrire ailleurs sur le disque |

**Mode débogage** (Réglages › Moteur, `[debug] enabled`, coupé par défaut) : le moteur écrit à côté de chaque
capture un journal `capture-<id>.json` (pays de StreetCLIP, zones, ce que l'IA a lu et sa conclusion, temps,
étiquette « C'était où ? »), pour relire une manche après coup. Local, supprimé avec les anciennes captures.

Un test vérifie que chaque clé de la configuration est soit modifiable à l'écran, soit dans cette liste : un
réglage ajouté sans être rangé fait échouer les tests. La liste des modèles NVIDIA est publique :
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
- Chaque astuce est rangée dans une catégorie de metas par ses étiquettes Plonk It (30 %), puis par
  mots-clés (`[plonkit] keywords`, 45 %), puis par l'IA pour le reste (`ai_classify`, désactivable) : par
  lots de 25, une seule fois par texte (cache), et seules les 12 catégories connues sont acceptées.
  Mesuré le 2026-11-07 : 1 009 astuces classées en 2 min 40 ; 92 % des astuces ont une catégorie ;
  environ 8 sur 10 sont justes sur un échantillon, les erreurs touchant surtout la caméra Google.

- **Traduction** : les guides sont en anglais. Les astuces affichées sont traduites à la demande dans la
  langue du coach (`[coach] language`, `fr` par défaut ; `en` = pas de traduction), par le modèle NVIDIA,
  avec un glossaire GeoGuessr (bollard → borne, road line → marquage…). L'anglais s'affiche d'abord ; les
  traductions arrivent par lots de 3 envoyés en parallèle (~10 s par lot mesuré avec Nemotron Super VL),
  puis sont gardées en cache : une astuce déjà lue s'affiche traduite immédiatement. « Voir l'original »
  permet de comparer. Désactivable (`[plonkit] translate`) ; modèle réglable (`[plonkit] ai_model`).

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

## Carte

La fenêtre a trois onglets, en bas : **Coach**, **Carte** et **Réglages** ; les niveaux d'aide restent en haut.
L'onglet **Carte** s'ouvre à partir du niveau 3 et occupe toute la fenêtre ; un point bleu s'y allume quand de
nouvelles zones sont prêtes. Aux niveaux 1 et 2, l'onglet est grisé : la carte dévoilerait les pays. Elle montre :
- les **pays probables** selon StreetCLIP, d'autant plus colorés qu'ils sont probables ;
- avec une **preuve certaine** : le pays prouvé en bleu, les autres candidats grisés et barrés, et les seules
  zones du pays prouvé, comme dans la liste des pays ;
- avec une **lecture de l'IA** (très probable, à confirmer) : ce pays est cerné de bleu en pointillés et ses
  zones passent en tête ; les autres pays restent colorés. Les astuces Plonk It le mettent aussi en premier ;
- les **zones probables** : le moteur garde les 80 % de positions PLONK les plus denses, les regroupe (deux
  positions à moins de 150 km vont ensemble) et trace un contour arrondi autour de chaque groupe d'au moins
  5 % des positions. Chaque zone est numérotée avec sa part des positions ; sous la carte, la liste donne ses
  pays et sa taille (« 1. 🇸🇪 Suède · ~450 × 450 km · 50 % des positions »). C'est une piste, pas une preuve :
  les zones tombent en général à 100–300 km du lieu quand le pays est juste.

Sur les 5 captures du jeu de test : une zone de ~150 × 200 km dans le sud-ouest de la Norvège (vue au nord
d'Ålesund) ; pour la Suède, une zone autour de Göteborg (50 %) et une en Finlande (30 %) ; pour la Lituanie,
une zone à cheval sur la Pologne et la Lituanie.

La carte se cadre seule sur les zones, ou sur les pays probables tant qu'elles ne sont pas prêtes ; au
niveau 4, une preuve forte la resserre sur son pays. Si la fenêtre est agrandie, la carte prend toute la
largeur.

**Fond de carte et confidentialité.** Le fond vient des tuiles **OpenStreetMap, en ligne**, assombries par un
filtre CSS pour le thème du coach. Le serveur de tuiles voit donc ton adresse IP et les zones affichées, à peu
près le lieu de la manche. Le coach suit les [règles d'usage](https://operations.osmfoundation.org/policies/tiles/)
d'OpenStreetMap : User-Agent propre à l'application (`GeoNesClick/0.1`), attribution toujours visible,
seules les tuiles affichées sont chargées (cache normal du navigateur, aucun téléchargement à l'avance),
zoom limité à 10 par défaut. Sans réseau, la carte garde les pays et le nuage, sans fond.

**Données locales.** Contours des pays : Natural Earth 1:50m v5.1.2 (domaine public), dans
`engine/src/geonesclick/data/`, servis par le moteur (`GET /map/countries`) et utilisés pour savoir dans quel
pays tombe chaque point du nuage (enclaves comprises, comme le Lesotho). PLONK : poids
`nicolas-dufour/PLONK_OSV_5M` (safetensors, 144 Mo) téléchargés une fois dans le cache Hugging Face au premier
démarrage ; le moteur passe ensuite hors ligne. Le code du réseau est repris du dépôt PLONK (licence MIT,
notice dans `engine/src/geonesclick/plonk.py`), réduit à ce que demande ce modèle : aucune dépendance
Python en plus.

**Réglages** : `[map]` (activation, serveur de tuiles, attribution, filtre, zoom maximal) et `[plonk]`
(activation, pas, points ; zones : `zone_share`, `zone_link_km`, `zone_min_part`). L'écran Réglages change l'activation, les pas, les points et le zoom ; le serveur de
tuiles, l'attribution et le filtre ne se changent que dans le fichier. **Un autre serveur de tuiles doit aussi
être autorisé** dans la politique de sécurité de la fenêtre (`img-src` de la CSP, dans
`app/src-tauri/tauri.conf.json`), et le lien de son attribution dans `app/src-tauri/capabilities/default.json`.

## Bancs d'essai

Chaque choix technique est mesuré sur le jeu de test (`engine/dataset/`) avant d'entrer dans le coach.
Les bancs sont dans `engine/spikes/` et se lancent depuis `engine/` :

| Banc | Mesure | Commande |
|---|---|---|
| `streetclip_bench.py` | mémoire vidéo, latence et top 5 de StreetCLIP | `.venv/bin/python spikes/streetclip_bench.py [image.png]` |
| `vlm_probe.py` | réponse et latence d'un modèle de vision NVIDIA | `.venv/bin/python spikes/vlm_probe.py [--model ID] image.png` |
| `compare_views.py` | fenêtre entière, vue recadrée, interface masquée | `.venv/bin/python spikes/compare_views.py [--no-vision]` |
| `streetclip_tta.py` | moyenne sur plusieurs recadrages | `.venv/bin/python spikes/streetclip_tta.py` |
| `search_bench.py` | moteurs de recherche sur les astuces Plonk It | `uv run --with tantivy==0.26.2 python spikes/search_bench.py` |
| `plonk_bench.py` | nuage GPS de PLONK, pays, dispersion, coût | voir ci-dessous |

**Banc PLONK.** PLONK n'est pas une dépendance du coach : son code et ses dépendances sont installés à
part, dans `engine/spikes/.vendor/` (ignoré par git), sans toucher au venv du moteur.

```bash
scripts/setup-plonk-spike.sh                        # une fois, puis à chaque changement de version
cd engine && .venv/bin/python spikes/plonk_bench.py # 512 points par défaut ; un nombre en argument sinon
```

Le script récupère le code PLONK figé sur un commit, `einops`, `geoopt`, `torchdiffeq` et `scipy` en
versions figées (sans leurs dépendances : torch et numpy viennent du venv) et les frontières Natural
Earth v5.1.2. Le banc télécharge ensuite les poids `nicolas-dufour/PLONK_OSV_5M` (safetensors, 144 Mo)
dans le cache Hugging Face. Il charge seulement le réseau et l'échantillonneur de PLONK, sans son
`__init__.py` qui tirerait `torchvision` et DINOv2.

## Outils et licences

| Outil | Rôle | Licence ou conditions |
|---|---|---|
| [Tauri 2](https://v2.tauri.app), [Vue 3](https://vuejs.org), [Tailwind 4](https://tailwindcss.com) | fenêtre du coach | MIT / Apache-2.0 |
| [FastAPI](https://fastapi.tiangolo.com), Uvicorn | serveur local du moteur | MIT / BSD-3 |
| GStreamer, PipeWire, portail ScreenCast (PyGObject) | capture de la fenêtre | LGPL |
| [PyTorch](https://pytorch.org), [Transformers](https://github.com/huggingface/transformers) | exécution de StreetCLIP | BSD-3 / Apache-2.0 |
| [StreetCLIP](https://huggingface.co/geolocal/StreetCLIP) (`geolocal/StreetCLIP`) | niveau 1, pays probables | **CC BY-NC 4.0 : pas d'usage commercial** |
| [API NVIDIA](https://build.nvidia.com), Nemotron 3.5 Super VL | niveau 2, fiche d'indices | conditions de service NVIDIA, clé personnelle |
| SQLite FTS5 | recherche dans les astuces | domaine public |
| [Plonk It](https://www.plonkit.net) | guides par pays | collectés en local pour ton usage, jamais redistribués |
| [PLONK](https://github.com/nicolas-dufour/plonk) (`PLONK_OSV_5M`) | nuage de positions de la carte (code réduit embarqué) | MIT (code et poids) ; entraîné sur OSV-5M, images Mapillary CC BY-SA 4.0 |
| [Natural Earth](https://www.naturalearthdata.com) 1:50m | contours des pays, pays d'un point | domaine public |
| [Leaflet](https://leafletjs.com) 1.9.4 | carte de l'interface | BSD-2 |
| [Tuiles OpenStreetMap](https://www.openstreetmap.org/copyright) | fond de carte, en ligne | données ODbL, attribution obligatoire ; [règles d'usage des tuiles](https://operations.osmfoundation.org/policies/tiles/) |
| [uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io), [cargo](https://rustup.rs) | installation | MIT / Apache-2.0 |

La licence de StreetCLIP interdit à elle seule tout usage commercial du coach.

## Maintenance

**Mettre à jour** : `git pull`, puis `scripts/install.sh` (relançable sans risque : il resynchronise le
venv avec `uv.lock` et le front avec `pnpm-lock.yaml`). Pour le banc PLONK, relance aussi
`scripts/setup-plonk-spike.sh`.

**Changer une version** :
- dépendances Python : `cd engine && uv add <paquet>==<version>` (met à jour `pyproject.toml` et
  `uv.lock`), puis `.venv/bin/python -m pytest -q` ;
- dépendances du front : `cd app && pnpm update <paquet>` ;
- banc PLONK : modifier `PLONK_COMMIT` et `DEPS` en tête de `scripts/setup-plonk-spike.sh`, relancer le
  script puis le banc.

**Où sont les données** (rien de tout cela n'est versionné) :

| Emplacement | Contenu | Si on le supprime |
|---|---|---|
| `~/.config/geonesclick/config.toml` | tes réglages | retour aux valeurs par défaut |
| `~/.config/geonesclick/mes-metas.toml` | tes metas et verdicts sur l'amorce | perdus : à sauvegarder |
| `~/.config/geonesclick/screencast.token` | autorisation de partage de GNOME | GNOME redemande la fenêtre |
| `~/.local/share/geonesclick/plonkit/` | guides Plonk It, astuces, vecteurs, traductions | reconstruit au démarrage (~3 min, traductions refaites à la demande) |
| `~/.cache/huggingface/hub/` | poids StreetCLIP et PLONK | retéléchargés au prochain lancement (réseau requis) |
| `engine/dataset/` | jeu de test (images + `labels.toml`) | perdu : à sauvegarder, c'est la base de toutes les mesures |
| `engine/captures/` | captures des manches ; en mode débogage, le journal `capture-<id>.json` de chaque analyse | sans conséquence |
| `engine/spikes/.vendor/` | code et dépendances du banc PLONK | `scripts/setup-plonk-spike.sh` le refait |

**Hors ligne** : une fois StreetCLIP et PLONK (s'il est activé) en cache, le moteur passe Hugging Face en
mode hors ligne au démarrage. Pour récupérer une nouvelle version d'un modèle, supprime son dossier
(`~/.cache/huggingface/hub/models--geolocal--StreetCLIP`, `models--nicolas-dufour--PLONK_OSV_5M`) et relance.

**Mettre à jour PLONK ou Natural Earth** : les poids sont figés sur une révision Hugging Face (`[plonk] revision`,
celle qui a été mesurée) ; pour en changer, remplacer `revision`, relancer `spikes/plonk_bench.py` et comparer.
Le code du réseau PLONK est figé dans `plonk.py` (commit 76d4641) ;
après un changement du dépôt d'origine, refaire le banc (`scripts/setup-plonk-spike.sh` avec le nouveau
commit, puis `spikes/plonk_bench.py`) et comparer avec le module du moteur avant de le modifier. Les
contours viennent de Natural Earth v5.1.2 ; pour une autre version, remplacer
`engine/src/geonesclick/data/ne_50m_admin_0_countries.geojson` (le champ `ISO_A2_EH` doit exister) et
relancer les tests.

**Avant chaque commit** : les tests (`cd engine && .venv/bin/python -m pytest -q`, sans aucun accès
réseau), puis une revue de code et une revue de sécurité.

## Architecture

```
Raccourci GNOME ─► moteur Python (FastAPI, 127.0.0.1:47615) ◄─ WebSocket ─► fenêtre Tauri + Vue
                     │
                     ├─ capture : portail ScreenCast + PipeWire + GStreamer (flux continu)
                     ├─ niveau 1 : StreetCLIP local (pays probables) + metas + astuces Plonk It
                     │    └─ carte : PLONK local sur le même vecteur (nuage de positions, arrière-plan)
                     └─ niveau 2 : modèle de vision NVIDIA (fiche d'indices, asynchrone)
fenêtre Tauri ── tuiles OpenStreetMap (en ligne, fond de la carte seulement)
```

| Élément | Choix | Configurable |
|---|---|---|
| Interface | Tauri 2 + Vue 3 + Tailwind 4 | — |
| Moteur | Python 3.12, FastAPI + WebSocket | port, origines autorisées |
| Capture | Portail ScreenCast + PipeWire + GStreamer | recadrage, masques, notification, son |
| Niveau 1 | StreetCLIP (`geolocal/StreetCLIP`) | modèle, prompt, liste de pays, top N |
| Niveau 2 | `nvidia/nemotron-3.5-super-vl-120b-a12b` | modèle, prompt, raisonnement, délai |
| Metas | tes metas, amorce, guides Plonk It collectés en local (SQLite + vecteurs CLIP) | activation, rafraîchissement, mots-clés, nombre d'astuces |
| Carte | Leaflet + tuiles OSM ; PLONK (`nicolas-dufour/PLONK_OSV_5M`) ; Natural Earth | activation, pas, points, serveur de tuiles, filtre, zoom |

**Sécurité** : le moteur n'écoute que sur `127.0.0.1` et refuse toute origine web inconnue (un site
ouvert dans le navigateur ne peut ni déclencher de capture ni lire les résultats). Le socket du
raccourci est en `0600`. La clé API ne quitte que vers l'API NVIDIA. La fenêtre du coach ne charge
d'images extérieures que depuis `tile.openstreetmap.org` (CSP `img-src`) et n'ouvre dans le navigateur que
les pages Plonk It et la page de copyright d'OpenStreetMap.

## Arborescence

```
app/                      interface Tauri + Vue
  src-tauri/src/lib.rs    lance et arrête le moteur
  src/engine.ts           connexion au moteur (WebSocket + HTTP)
  src/components/         pays (Countries), carte (CoachMap), ce que voit l'IA (Observations),
                          « C'était où ? » (LabelForm), réglages (SettingsPanel + SettingField)…
  src/settingsSchema.ts   description de chaque réglage de l'écran (libellé, aide, type, section)
engine/                   moteur Python
  src/geonesclick/     capture, StreetCLIP, PLONK (plonk.py), frontières (borders.py), vision, metas
                          (+ amorce), jeu de test, réglages, serveur
    data/                 contours des pays Natural Earth 1:50m (domaine public)
  spikes/                 bancs d'essai : StreetCLIP, modèle de vision, recadrage, multi-recadrage,
                          recherche, PLONK (code tiers du banc PLONK dans spikes/.vendor/, ignoré)
  dataset/labels.toml     jeu de test étiqueté (images locales dans dataset/images/, non versionnées)
  captures/               captures d'écran (ignorées par git)
scripts/install.sh        installation
scripts/setup-plonk-spike.sh  dépendances du banc PLONK, à part du venv du moteur
```
