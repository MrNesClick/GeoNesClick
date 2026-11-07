# GeoNesClick

> Anciennement « GeoNesClick » (renommé le 2026-11-07 : trop proche de la marque GeoGuessr). Au premier
> lancement, tes dossiers `~/.config/geonesclick` et `~/.local/share/geonesclick` sont **déplacés** vers
> `geonesclick` (jamais supprimés ; si les deux existent, rien n'est touché). Relance
> `scripts/install.sh --setup-shortcut` pour remplacer les anciens raccourcis GNOME.

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
- **Marques** : Super+Maj+Z fige la vue en plein écran ; tu entoures chaque indice (plaque de rue, panneau,
  enseigne…), numéroté ①, ②… Chaque marque est découpée dans l'image brute, agrandie si elle est petite, puis
  transcrite mot pour mot par l'IA. Ce sont tes éléments de preuve : les conclusions du coach les citeront.
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

## Ce que GeoNesClick télécharge

Tout accès réseau de l'application est listé dans [`engine/src/geonesclick/downloads.toml`](engine/src/geonesclick/downloads.toml),
affiché par l'assistant de premier lancement **avant le moindre téléchargement**, et repris ici. Un test vérifie que
chaque adresse écrite dans le code y figure. Les éléments obligatoires (sans eux l'app ne fait rien) demandent un seul
accord ; chaque option a le sien et se coupe ensuite dans les Réglages. PyTorch CUDA est choisi s'il y a une carte
NVIDIA, sinon la version processeur.

| Quoi | D'où | Taille | Licence | Quand | Ce qui part de ta machine |
|---|---|---|---|---|---|
| Python 3.12 (interpréteur autonome, python-build-standalone) **(obligatoire)** | `github.com`, `objects.githubusercontent.com` | 30 Mo | PSF-2.0 | une fois, à l'installation | — |
| Bibliothèques Python du moteur (PyTorch, Transformers, FastAPI…), versions figées et vérifiées par empreinte **(obligatoire)** | `pypi.org`, `files.pythonhosted.org` | 3,1 Go | variées (BSD, MIT, Apache-2.0…), liste détaillée paquet par paquet dans le tunnel | une fois, à l'installation | — |
| PyTorch pour processeur (à la place de la version CUDA, s'il n'y a pas de carte NVIDIA) **(obligatoire)** | `download.pytorch.org` | 200 Mo | BSD-3-Clause | une fois, à l'installation | — |
| Modèle StreetCLIP (geolocal/StreetCLIP, version figée, poids safetensors) **(obligatoire)** | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 1,7 Go | CC BY-NC 4.0 (usage non commercial) | une fois, à l'installation | — |
| Répertoire des lieux GeoNames (villes de plus de 1 000 habitants) et noms des régions | `download.geonames.org` | 11 Mo | CC BY 4.0 (GeoNames) | une fois, si tu l'acceptes | — |
| Villages d'un pays (répertoire complet GeoNames du pays en tête) | `download.geonames.org` | 8 Mo | CC BY 4.0 (GeoNames) | à la demande | — |
| Guides Plonk It (84 pages), puis contrôle des mises à jour tous les 30 jours | `www.plonkit.net` | 2 Mo | aucune licence de réutilisation : collectés pour ton usage personnel, jamais redistribués | une fois, si tu l'acceptes | — |
| Modèle PLONK (nicolas-dufour/PLONK_OSV_5M, version figée, safetensors) | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 144 Mo | MIT | une fois, si tu l'acceptes | — |
| Analyse par le modèle de vision NVIDIA (API en ligne) | `integrate.api.nvidia.com` | — | conditions d'utilisation de l'API NVIDIA (build.nvidia.com) ; ta clé API | à chaque usage | tes captures (réduites à 1 280 px), les découpes de tes marques et les astuces à traduire |
| Fond de carte OpenStreetMap (tuiles) | `tile.openstreetmap.org` | — | données © contributeurs OpenStreetMap (ODbL) ; politique d'usage des tuiles de l'OSMF | à chaque usage | ton adresse IP et les zones de carte affichées |

Licence à connaître : StreetCLIP est sous **CC BY-NC 4.0**, usage **non commercial** uniquement.

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
scripts/install.sh --setup-shortcut # ajoute les raccourcis GNOME : capture (Super+Maj+G), marques (Super+Maj+Z)
```

Le script peut être relancé sans risque, par exemple après chaque `git pull`. Ensuite, au premier lancement,
saisis ta clé API NVIDIA (gratuite sur [build.nvidia.com](https://build.nvidia.com), « Get API Key ») dans
**Réglages › Analyse**. Elle est rangée hors du dépôt, dans `~/.config/geonesclick/nvapi.key`, lisible par toi seul
(0600), et n'est jamais réaffichée (seulement ses 4 derniers caractères). La variable d'environnement `NVAPI`, si
elle est définie, reste prioritaire. Une clé encore dans l'ancien `.env` y est **déplacée** au démarrage (la
ligne est retirée du `.env`).

Pour changer les raccourcis : `GNC_SHORTCUT="<Super><Shift>h" GNC_MARK_SHORTCUT="<Super><Shift>m"
scripts/install.sh --setup-shortcut`.

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
  lu exactement (Roumanie) une fois la zone découpée et agrandie trois fois. D'où les marques, ci-dessous.

### Marques

Un détail compte (plaque de rue, panneau, enseigne, plaque d'immatriculation) ? Appuie sur **Super+Maj+Z**
(ou sur « Marquer ») : la vue est figée et s'ouvre en plein écran. Entoure chaque indice d'un rectangle ;
ils sont numérotés ①, ②… **Entrée** les fait lire, **Échap** annule, **Retour arrière** (ou clic droit)
retire la dernière. Des boutons font la même chose, au cas où GNOME ne donne pas le clavier à la fenêtre.

- Chaque marque est découpée dans l'image **brute**, en pleine résolution, puis **agrandie** si elle est
  petite (le plus grand côté porté à 420 px, ×4 au plus : `[marks] upscale_to_px`, `max_upscale`).
- L'IA la **transcrit seulement**, mot pour mot, avec ce qu'elle montre et l'alphabet ; elle ne nomme aucun
  pays. C'est le coach qui conclura, avec des règles locales sourcées (prochaine étape), en citant les marques.
- Les marques **complètent l'analyse de la manche** : capture d'abord (Super+Maj+G ouvre la manche), marque
  ensuite. La fenêtre des marques rappelle l'heure de la capture complétée, et la numérotation continue d'une
  vue figée à l'autre. Sans capture, le raccourci le signale et ne fige rien.
- En mode débogage, chaque découpe est gardée (`mark-<id>-<n>.png`) avec sa lecture dans le journal.
- L'écran des marques rappelle **ce qui est pris en compte**, et ce qui ne l'est pas encore (poteaux, bornes…).
- **Retirer** une marque (lecture fausse, découpe ratée) : elle ne compte plus, la réponse est recalculée.

### Ce que le coach conclut de tes marques

L'IA transcrit ; le coach conclut **en local**, avec des règles sourcées (`engine/src/geonesclick/evidence.py`),
et la réponse cite les marques qui la prouvent :

| Règle | Exemple | Effet |
|---|---|---|
| **Alphabet** | du cyrillique | écarte les pays qui ne l'écrivent pas (la France, même si l'IA a « lu » du français sur la vue entière) |
| **Lettres propres** | « ъ » devant une consonne, « ő », « ș » | langue → pays **très probable** |
| **Mots de rue** | « utca », « iela », « -katu », « вулиця » | langue → pays **très probable** |
| **Noms de lieux** (GeoNames) | Благоевград, София | pays **certain**, s'il est confirmé par une autre preuve et qu'**aucune marque ne le contredit** |
| **Lieu seul** | « MANTO » | simple **indice** : il faut un 2ᵉ lieu voisin, une lettre ou un mot de la langue, ou StreetCLIP à 10 % au moins (`prior_min`) |
| **Nom de rue** | « Via Paolo Lo Manto », « Main Street » | ne situe pas la vue : ses mots ne sont pas des lieux (affiché « Rue ») |
| **Pays hors candidats** | Manto → 🇭🇳 | affiché, ne compte pas |

Mesuré le 2026-11-07 : en une journée, les lieux **seuls** se sont trompés quatre fois (Gare → 🇫🇷🇱🇺, Laas → 🇮🇹,
Orion → 🇵🇭🇺🇸, et « Lo Manto », tiré du nom de rue « Via Paolo Lo Manto », → 🇭🇳, qui renversait l'Italie de
StreetCLIP à 96 %), alors que les conclusions justes venaient de lieux **groupés**.

Pourquoi si prudent ? Mesuré le 2026-11-07 sur une manche bulgare : la marque ① (« Гърмен 3, Гоце Делчев 10,
Благоевград 109, София 219 ») a été lue parfaitement, mais la ②, floue, a été **inventée** en russe plausible
(« Домой, Город, Казань »), et l'analyse de la vue entière avait inventé du français (« Gare, Centre-ville,
Mairie »). Avec les deux marques, le coach répond « Bulgarie, très probable » et signale ② ; une fois ② retirée,
« Bulgarie, certain ». Un mot courant peut aussi nommer un lieu (« Gare » : quartiers en France et au
Luxembourg), d'où la concordance exigée. Seuls comptent les pays candidats (la Moldavie n'empêche pas « ș » de
désigner la Roumanie).

**Position sur la carte.** Les lieux lus sont placés sur la carte. Les distances d'un panneau directionnel
(« Гърмен 3, Гоце Делчев 10, Благоевград 109, София 219 ») donnent une **position estimée** par triangulation
(`locate.py`) : ce sont des distances par la route, converties à vol d'oiseau (détour ×1,15 à ×1,45), en erreur
relative, si bien que les lieux proches fixent le point. Mesuré sur ce panneau : 41,58° N, 23,83° E, à 2-3 km de
Гърмен, annoncé à 2 km près (pas encore de vérité terrain pour le confirmer). L'IA lit parfois mal un chiffre
(« 6 » puis « 8 » sur une même marque) : si les distances ne concordent pas, **pas de point**. Le coach désigne la
distance à vérifier et ne garde que ce qui reste vrai (la vue est à moins de *d* km du lieu le plus proche).
**Panneaux recopiés colonne par colonne.** L'IA recopie souvent un panneau directionnel ligne par ligne, chiffres à
part. Le coach le relit comme un tableau (mesuré le 2026-11-07 sur trois panneaux) : une distance après le nom, sur
sa ligne, n'est jamais remplacée ; des nombres seuls qui suivent un bloc de lieux leur reviennent dans l'ordre s'ils
sont aussi nombreux (« 329 Faaborg », « Glamsbjerg », « 28 », « 3 » : Faaborg 28, Glamsbjerg 3, le 329 était une
route) ; sinon un nombre seul juste sous un lieu lui revient (« SARANSK », « 162 ») ; enfin, un nombre devant le nom
compte (« 10 Aarup »). Un nombre en trop est un numéro de route, ignoré (« 5 Ørsted », « 329 » ; « Гърмен 3 », « 197 »).
Reste indécidable par le texte seul : « 329 Faaborg » sans autre chiffre ; la cohérence des distances le signale.

Limite : un chiffre faux mais géométriquement plausible (« 8 » pour « 3 » entre deux villages voisins) passe ce
contrôle, avec quelques km d'erreur.

**Homonymes et petits villages.** Mesuré le 2026-11-07 sur une manche du Béarn : « LAAS » (village de 108
habitants, absent du répertoire général) tombait sur Lasa, en Italie (« Laas » en allemand), et contredisait à
tort la France ; « ORION » (de L'Hôpital-d'Orion) tombait aux Philippines. D'où :
- **la proximité** : les lieux d'une même manche sont voisins. Le coach garde le groupe de lieux le plus fourni
  (à moins de 400 km les uns des autres, `[rules] place_max_spread_km`) et ignore les homonymes lointains,
  affichés barrés ; sans groupe d'au moins deux lieux, rien n'est écarté. Parmi les homonymes du groupe, il
  retient le plus proche (Laàs du Béarn, à 13 km d'Orthez, et non Laas du Gers, à 87 km) ;
- **les villages du pays en tête** : dès qu'un pays mène, son répertoire GeoNames complet (lieux habités
  seulement ; France 7,3 Mo, 1,8 s d'indexation) est téléchargé une fois, puis les marques sont relues
  (`[rules] detail`). Sur cette manche : L'Hôpital-d'Orion, Sauveterre-de-Béarn, Orthez et Laàs trouvés,
  « France, certain ». GeoNames voit alors quel pays est consulté ;
- la comparaison ignore les accents latins, les traits d'union et l'article en tête (« SAUVETERRE DE BEARN »
  = Sauveterre-de-Béarn, « HOPITAL D'ORION » = L'Hôpital-d'Orion).

Le répertoire des lieux est celui des localités de plus de 1 000 habitants de [GeoNames](https://www.geonames.org)
(licence [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)), téléchargé une fois (~11 Mo) par
`scripts/install.sh` ou au premier démarrage, puis indexé en local (~55 Mo, 918 000 noms dans toutes les langues).
Chaque règle se coupe dans Réglages › Marques (`[rules]`). La région de chaque lieu (code GeoNames « admin1 ») est
indexée aussi, avec le nom des régions (`admin1CodesASCII.txt`, ~140 Ko, téléchargé une fois ; sans réseau, la
région s'affiche par son code) : elle sert aux verrous.

### Verrous

En tête du coach, « **Tu sais où tu es ? Dis-le au coach** » : la liste des pays (les plus probables d'abord, dès
le niveau 3) ; un clic, et la ligne devient « C'est sûr : 🇨🇿 Tchéquie (toi) ✕ », puis Région et Ville se
choisissent de la même façon. Ce qui est sûr (le « verrou ») restreint la recherche suivante : lieux et homonymes
du pays, villages de la région, zones de la carte et astuces Plonk It du pays. Décidé le 2026-11-07 :

- **le coach** verrouille seul le pays quand tes marques le rendent **certain** (jamais sur « très probable »), et la
  région quand la position estimée est un point net (panneau aux distances cohérentes) et que tous les lieux à
  moins de 10 km de ce point sont de la même région (ou « à moins de N km de tel lieu », N ≤ 10, quand les distances
  sont incohérentes : la plus courte reste vraie) ; sans distance lue, quand au moins deux lieux lus sont dans la
  même région, à moins de 50 km l'un de l'autre (`region_places_km`). Un lieu seul ne suffit pas. Quand tes lieux
  se partagent entre régions (« Oker » en Basse-Saxe, « Retz » → Rötz en Bavière), il te les propose en boutons. Une **ville**, il ne fait que la **proposer** (« Laàs ? », un
  clic pour la verrouiller) : un panneau « Pau 40 km » nomme justement un lieu où tu n'es pas. Ses verrous suivent
  les preuves : une marque retirée peut les défaire ;
- **toi**, tu peux toujours dire « pas ça » (✕) : écarté pendant toute la capture, le coach ne le repropose pas.
  Tu peux aussi le dire toi-même (liste ou recherche dans l'index local, sans réseau ; ou « c'est ici » sur un lieu
  lu dans tes marques). Le coach ne remplace jamais ton choix ; une ville choisie fixe aussi sa région et son pays ;
- **les avis indépendants restent indépendants** : la Réponse tirée de tes marques ne tient compte ni de ton
  choix ni de tes ✕ ; le bandeau dit si elle le confirme (« ✓ tes marques le confirment : ① ř, ů, ě ») ou le
  contredit (« ⚠ tes marques désignent la Pologne »), de même pour StreetCLIP et l'IA. C'est ce qui révèle un choix
  faux. Contradiction forte (autre pays « certain », ou alphabet qui exclut ton pays) : alerte en tête et deux
  sorties en un clic, « Passer à 🇵🇱 Pologne » ou « ① est mal lue : la retirer » (l'erreur peut venir de toi ou de
  la lecture) ; le coach ne change jamais ton choix lui-même. Ton choix ne restreint que la suite : homonymes
  retenus pour la position, région, ville proposée ;
- un verrou du coach ne se nomme qu'au niveau d'aide qui le dévoile (pays au niveau 3, région et ville au 4) ; en
  dessous, le bandeau dit « le coach en est sûr (caché à ce niveau d'aide) » ;
- les verrous **durent une capture** : une nouvelle capture repart de zéro (un verrou périmé fausserait la manche
  suivante). En mode débogage, chaque verrou et chaque rejet est journalisé dans `capture-<id>.json`.

Réglages › Ce qui est sûr (`[locks]`) : activation, pays et région fixés seuls par le coach, ville proposée, rayon.

Pour lancer le moteur seul (sans interface) : `cd engine && .venv/bin/python -m geonesclick`.

## Tests

```bash
cd engine && .venv/bin/python -m pytest -q
```

Ils couvrent la configuration, le recadrage et les masques, la réponse du modèle de vision, les metas et
le départage, le jeu de test et la progression, les marques (découpe, agrandissement, numérotation), les réglages (liste blanche, écriture atomique), et les
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
  En pratique, à la demande ne suffit pas : le 2026-11-07, 31 astuces sur 4 060 étaient en cache, et une manche
  a attendu plus de 2 min un lot qui ne revenait pas. D'où :
  - **la traduction d'avance** de toute la base, en arrière-plan, par lots de 10, toujours après les manches en
    cours ; elle reprend où le cache s'arrête (`[plonkit] pretranslate`, progression dans Réglages › Indices) ;
  - **un délai court** par lot affiché (`[plonkit] translate_timeout_s`, 30 s, sans nouvel essai) : passé ce
    délai, ou si le modèle oublie une astuce, elle reste en anglais et le coach le dit, au lieu d'attendre.
  En mode débogage, chaque lot (durée, astuces rendues, erreur) est noté dans le journal de la manche.

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
zoom limité à 13 par défaut (`[map] max_zoom`, réglable : 13 montre les rues autour d'une position estimée par
tes marques ; les zones et les pays se cadrent toujours au zoom 8 au plus). Le fond assombri (couleurs inversées)
devient illisible de près (forêts et relief en taches, noms de villages noyés, constaté au zoom 13) : à partir du
zoom 11 (`close_zoom`), les tuiles d'origine reviennent, à peine atténuées (`tile_filter_close`). Dès que tes
marques situent la vue, les zones PLONK sont masquées : elles ne viennent que de l'allure de la vue et
contrediraient la preuve (Nord-Est et Aquitaine affichés pour une manche en Béarn). Sans réseau, la carte garde les pays,
le nuage et les lieux lus, sans fond.

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

Chaque choix technique est mesuré sur le jeu de test avant d'entrer dans le coach. Les bancs de `spikes/` lisent
l'exemplaire versionné dans le dépôt (`engine/dataset/`) ; le coach enregistre les nouvelles manches dans
`~/.local/share/geonesclick/dataset/`.
Les bancs sont dans `engine/spikes/` et se lancent depuis `engine/` :

| Banc | Mesure | Commande |
|---|---|---|
| `streetclip_bench.py` | mémoire vidéo, latence et top 5 de StreetCLIP | `.venv/bin/python spikes/streetclip_bench.py [image.png]` |
| `vlm_probe.py` | réponse et latence d'un modèle de vision NVIDIA | `.venv/bin/python spikes/vlm_probe.py [--model ID] image.png` |
| `compare_views.py` | fenêtre entière, vue recadrée, interface masquée | `.venv/bin/python spikes/compare_views.py [--no-vision]` |
| `streetclip_tta.py` | moyenne sur plusieurs recadrages | `.venv/bin/python spikes/streetclip_tta.py` |
| `search_bench.py` | moteurs de recherche sur les astuces Plonk It | `uv run --with tantivy==0.26.2 python spikes/search_bench.py` |
| `plonk_bench.py` | nuage GPS de PLONK, pays, dispersion, coût | voir ci-dessous |
| `geonesclick.bench` | règles des marques rejouées sur tes manches : fausses certitudes, région, km | `.venv/bin/python -m geonesclick.bench [--json]` |

**Banc de relecture des marques** (`python -m geonesclick.bench`, depuis `engine/`). Décidé le 2026-11-07 : on
ne règle plus les règles locales au cas par cas sur la dernière manche (la règle écrite pour un panneau russe a
cassé un panneau danois vingt minutes plus tard), mais sur l'ensemble. À chaque « C'était où ? », le coach garde
dans `~/.local/share/geonesclick/dataset/rounds/<id>.json` le texte de tes marques et ce qu'il avait conclu ; si tu colles le lien
Google Maps du vrai lieu (écran de fin du jeu), il en lit les coordonnées (sans jamais l'ouvrir) et en déduit pays
et région. Le banc rejoue toutes ces manches dans les règles ACTUELLES (même code que le moteur, index local, aucun
réseau) et compte : pays certain juste / faux, très probable, région juste / fausse, erreur de position en km, et
si le vrai lieu est dans le rayon annoncé. Une règle ou un seuil ne change que si le banc s'améliore sans casser une
manche qui marchait ; la cible est **zéro fausse certitude**. `--json` pour comparer deux versions.

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

**Code de GeoNesClick : licence [Apache-2.0](LICENSE)** (© 2026 MrNesClick). Les modèles et données téléchargés au
premier lancement gardent leur propre licence (voir « Ce que GeoNesClick télécharge ») : en particulier **StreetCLIP
est sous CC BY-NC 4.0, usage non commercial**, ce qui s'applique à toute utilisation de l'application qui s'en sert.

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
| `~/.local/share/geonesclick/places/` | répertoire des lieux GeoNames (CC BY 4.0), indexé | retéléchargé au démarrage s'il manque (~11 Mo) |
| `~/.cache/huggingface/hub/` | poids StreetCLIP et PLONK | retéléchargés au prochain lancement (réseau requis) |
| `~/.local/share/geonesclick/dataset/` | jeu de test (images, `labels.toml`, `rounds/` du banc) | perdu : à sauvegarder, c'est la base de toutes les mesures |
| `~/.local/share/geonesclick/captures/` | captures des manches ; en mode débogage, le journal `capture-<id>.json` de chaque analyse | sans conséquence |

Ces deux dossiers vivaient dans `engine/` jusqu'au 2026-11-07 (en lecture seule dans une AppImage) : au premier
lancement, les captures y sont déplacées et le jeu de test copié (l'exemplaire suivi par git reste dans le dépôt).
| `engine/spikes/.vendor/` | code et dépendances du banc PLONK | `scripts/setup-plonk-spike.sh` le refait |

**Réglages › Stockage** affiche la taille de chaque élément et un bouton **Vider** (en deux temps : Vider, puis
Confirmer, avec ce que ça coûte ; Plonk It prévient que les traductions d'avance sont à refaire). La taille
maximale (`[storage] max_cache_mb`, 500 Mo) ne s'applique qu'aux caches **qui grossissent** tout seuls (villages
des pays rencontrés) : les moins récemment utilisés partent d'abord. Le socle (répertoire GeoNames, guides
Plonk It) ne part jamais tout seul, et ton jeu de test, tes metas et ta config ne sont jamais vidés. Par
sécurité, seuls des fichiers connus du coach sont supprimés, jamais un dossier entier.

**Tout effacer** (droit à l'effacement, RGPD) : en bas de Réglages › Stockage. La liste de ce qui part s'affiche avec
les tailles : clé API, réglages, tes metas, autorisation de partage d'écran, captures et journaux, jeu de test (signalé
comme précieux), guides Plonk It et traductions, lieux GeoNames et villages, état de l'interface, raccourcis GNOME de
l'application. Une case à part, décochée : aussi les modèles téléchargés (StreetCLIP, PLONK : rien de personnel ;
les modèles d'autres logiciels restent). Il faut taper « EFFACER » ; puis le moteur et l'interface repartent de
zéro. Seuls des fichiers connus de l'application sont supprimés, jamais un dossier réglé à la main ni son contenu
étranger. L'exemplaire du jeu de test versionné dans le dépôt (`engine/dataset/`) n'est pas touché.

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
  src/components/         pays (Countries), carte (CoachMap), ce que voit l'IA (Observations), verrous
                          (Locks), « C'était où ? » (LabelForm), réglages (SettingsPanel + SettingField)…
  src/settingsSchema.ts   description de chaque réglage de l'écran (libellé, aide, type, section)
engine/                   moteur Python
  src/geonesclick/     capture, StreetCLIP, PLONK (plonk.py), frontières (borders.py), vision, metas
                          (+ amorce), marques et règles locales (marks_engine, evidence, places, locate),
                          verrous (locks, locks_engine), jeu de test, réglages, serveur
    data/                 contours des pays Natural Earth 1:50m (domaine public)
  spikes/                 bancs d'essai : StreetCLIP, modèle de vision, recadrage, multi-recadrage,
                          recherche, PLONK (code tiers du banc PLONK dans spikes/.vendor/, ignoré)
  dataset/labels.toml     jeu de test étiqueté (images locales dans dataset/images/, non versionnées)
  dataset/rounds/         corpus du banc : texte des marques et conclusion du coach, par manche
  captures/               captures d'écran (ignorées par git)
scripts/install.sh        installation
scripts/setup-plonk-spike.sh  dépendances du banc PLONK, à part du venv du moteur
```
