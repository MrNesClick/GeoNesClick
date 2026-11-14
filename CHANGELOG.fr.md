# Journal des modifications

Ce qui change d'une version de GeoNesClick à la suivante, pour les personnes qui l'utilisent. C'est la traduction de
[CHANGELOG.md](https://github.com/MrNesClick/GeoNesClick/blob/main/CHANGELOG.md), affichée par le panneau
**Nouveautés** quand l'interface est en français. Le format suit
[Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et les versions suivent le
[versionnage sémantique](https://semver.org/lang/fr/). Les notes de version publiées sur GitHub sont en anglais.

## [Non publié]

## [0.6.0] - 2026-11-14

### Modifié

- Dans une fenêtre large (1024 pixels et plus), le coach s'affiche sur deux colonnes : ce qui vous aide à décider
  (verrous, réponse, marques, où regarder ou les pays, ce qui les départage, astuces Plonk It) à gauche, les preuves (la
  capture, ce que voit l'IA, après la manche) à droite. La capture y est ouverte par défaut ; que vous l'ouvriez ou la
  repliiez, c'est retenu à part de la fenêtre étroite. Une fenêtre plus étroite garde la colonne unique.
- Le panneau **Nouveautés** est en français quand l'interface est en français, historique complet compris.

## [0.5.0] - 2026-11-13

### Ajouté

- GeoNesClick vous prévient quand une nouvelle version est sortie : une fois par jour au plus, il demande à GitHub
  quelle est la dernière version (votre adresse IP et la version de l'application partent, rien d'autre ; rien n'est
  téléchargé de lui-même). Un bandeau propose la page de la version ; **Plus tard** le ferme pour cette version, et
  Réglages › Général continue de l'indiquer, avec **Vérifier** et l'option pour couper la vérification. L'installateur
  la propose, cochée ; si vous mettez à jour depuis une version précédente, le coach vous dit une fois qu'elle est
  active.
- Une capture presque d'une seule couleur (noire, un écran de chargement) ou identique à la capture précédente (un
  partage d'écran figé) est quand même analysée, mais elle porte une note sous la capture et dans sa ligne de résumé,
  pour qu'une réponse sans valeur ne passe pas pour une vraie.

### Modifié

- Ouvrir une AppImage plus récente demande maintenant une fois s'il faut mettre à jour, en montrant ce qui a changé et
  ce qui serait téléchargé (souvent rien), avec **Plus tard** pour garder la version installée. Vos réglages, votre clé
  d'API et vos données sont gardés (ils revenaient aux choix recommandés, et la clé était redemandée), et seules les
  bibliothèques qui ont changé sont téléchargées (quelques Mo au lieu de 3,1 Go avec une carte NVIDIA). Pendant la
  mise à jour, une seule ligne dit ce qu'elle fait, en nommant ce qu'elle télécharge et sa taille ; ensuite le coach
  propose, une fois, ce qui a changé depuis votre version. Ouvrir une AppImage plus ancienne que celle installée ne
  change rien et propose d'ouvrir la version installée.
- GeoNesClick est maintenant installé sous `~/.local/share/geonesclick/GeoNesClick.AppImage` et lancé de là par le
  menu des applications : le fichier que vous avez téléchargé peut être renommé, déplacé ou supprimé (le coach vous le
  dit une fois), et l'entrée du menu ne se casse plus quand vous le faites. Tout effacer supprime cette copie avec le
  moteur.
- Le coach ne partage plus la fenêtre du jeu dès son ouverture : rien n'est partagé tant que vous ne cliquez pas sur
  **Partager la fenêtre du jeu**, qui partage alors la fenêtre retenue sans la boîte de dialogue de GNOME.
- Un pays lu dans vos marques est « certain » (mis en premier, les autres écartés, verrouillé par le coach) seulement
  quand une seconde source confirme la lecture : une seconde marque, ou l'allure de la vue (StreetCLIP donnant 10 % ou
  plus à ce pays). Sinon, une marque seule est « très probable », et la réponse dit qu'une seconde marque
  trancherait : un seul recadrage flou peut être inventé de bout en bout et rester cohérent.

### Corrigé

- Quand la fenêtre partagée la dernière fois n'existe plus, la partager n'affiche plus « partage d'écran actif » sans
  qu'aucune image n'arrive : le coach oublie cette fenêtre et ouvre le sélecteur de GNOME pour que vous choisissiez la
  fenêtre du jeu. Le partage ne compte comme actif qu'à partir de sa première image.
- L'IA locale démarre sur une capture sans attendre que sa copie sur le disque soit écrite : sa réponse arrive environ
  0,35 s plus tôt sur un écran de 1920 pixels de large, 1,3 s en 4K. La notification « capture prise » arrive une fois
  la copie écrite.

## [0.4.1] - 2026-11-13

### Sécurité

- Les barres du navigateur (titres des onglets, adresse, favoris) ne partent plus avec vos captures vers le modèle de
  vision de NVIDIA, et n'atteignent plus l'IA locale. Le coach trouve où commence la page du jeu dès la première
  capture, grâce à la ligne que le navigateur trace sous ses barres, et aussi en comparant les captures, ce qui marche
  quel que soit le navigateur. Si aucune des deux ne la trouve, il coupe une part fixe du haut de la fenêtre et vous le
  dit sous la capture. Une zone réglée à la main dans `config.toml` (`[capture] crop`) reste prioritaire.

### Corrigé

- Une fenêtre de navigateur redimensionnée après le début du partage d'écran est maintenant analysée sans les bandes
  noires autour. GNOME garde l'image partagée à sa première taille et remplit le reste de noir : l'IA locale et le
  modèle de vision voyaient ces bandes comme une partie de la vue.

## [0.4.0] - 2026-11-13

### Modifié

- Sans preuve lue sur la vue, le coach ne donne un pays comme réponse que quand l'allure de la vue (StreetCLIP) lui
  donne au moins 70 % (40 % jusqu'ici). Sur le jeu de test, toutes les réponses au-dessus de 70 % étaient justes, alors
  que 3 sur 8 entre 40 et 70 % étaient fausses ; sous 70 %, le coach parle d'hésitation entre les premiers pays. Le
  seuil peut toujours être changé dans les Réglages.

## [0.3.2] - 2026-11-13

### Corrigé

- Avec `XDG_CACHE_HOME` défini, le coach cherchait les modèles d'IA dans le mauvais dossier : l'analyse locale
  contactait Hugging Face à chaque démarrage au lieu de rester hors ligne, et « Tout effacer » laissait les modèles sur
  le disque (1,7 Go pour StreetCLIP).
- L'installateur nomme les dossiers où vont réellement le moteur et les modèles, quand `XDG_DATA_HOME`, `HF_HOME` ou
  `XDG_CACHE_HOME` pointent ailleurs.

## [0.3.1] - 2026-11-13

### Corrigé

- Les raccourcis clavier ne faisaient rien quand le chemin du dossier personnel (ou de `XDG_DATA_HOME`) contient une
  espace. Les raccourcis déjà ajoutés sont réparés au lancement suivant, sans rien à faire.
- Quand l'installateur ne pouvait pas ajouter les raccourcis clavier ou l'entrée de menu, il passait au coach sans le
  dire. Il affiche maintenant l'erreur à sa dernière étape, et le coach démarre avec « Lancer quand même ».

## [0.3.0] - 2026-11-12

### Ajouté

- GeoNesClick peut être ajouté au menu des applications, ce qui lui donne aussi sa propre icône dans le dock au lieu
  d'une icône générique : une option de l'installateur, désactivée par défaut. L'entrée suit l'AppImage quand elle est
  ouverte depuis un autre endroit, et « Tout effacer » la supprime.
- Un groupe « Intégration GNOME » dans les Réglages active ou désactive à tout moment les raccourcis clavier et
  l'entrée de menu.

### Corrigé

- Le groupe « Marques » des Réglages affiche un résumé d'une ligne, comme les autres groupes.
- Après une désinstallation depuis « Tout effacer », aucun dossier `geonesclick` vide ne reste dans `~/.local/share`,
  et le résumé du stockage n'affiche plus la taille mesurée avant.

## [0.2.5] - 2026-11-12

### Corrigé

- « Tout effacer » avec la case des modèles laissait leurs poids sur le disque (1,7 Go pour StreetCLIP) et affichait
  leur taille comme quelques Mo : la bibliothèque Hugging Face récente les garde dans un stockage partagé, qui est
  maintenant compté et vidé (jamais un fichier qu'un autre programme utilise encore).
- Après une désinstallation depuis « Tout effacer », la liste du stockage n'affiche plus les tailles mesurées avant.
- L'aide de la taille du cache n'annonce plus des fonctions qui n'existent pas.

## [0.2.4] - 2026-11-12

### Ajouté

- « Tout effacer » peut aussi supprimer le moteur installé par l'AppImage : avec la case des modèles en plus, c'est
  une désinstallation complète depuis l'application, après laquelle il ne reste que l'AppImage.

### Modifié

- Marques : l'interface dit « encadrez » un indice, puisque vous tracez un rectangle.

### Corrigé

- L'aide de « Une preuve lue tranche » citait des règles locales qui n'existent pas (domaine, indicatif téléphonique).
- La liste de ce qui est envoyé à NVIDIA inclut maintenant les astuces Plonk It qu'il classe et traduit.
- L'installateur disait « rien n'est modifié dans le système » juste après avoir installé un composant système
  manquant.

## [0.2.3] - 2026-11-12

### Modifié

- Un composant système manquant s'installe d'un clic sur plus de systèmes : avec `apt` (Debian, Ubuntu), `dnf`
  (Fedora), `pacman` (Arch) ou `zypper` (openSUSE), avec les noms de paquets de chacun ; la commande affichée est celle
  de votre système.

### Corrigé

- L'écran des Réglages ne reste plus sur « Chargement des réglages… » quand il a été ouvert pendant que le moteur
  démarrait encore (premier lancement) : il se charge dès que le moteur répond.
- Sans carte NVIDIA, les premières captures n'attendent plus des minutes que les astuces Plonk It soient préparées
  (environ 5 minutes sur un processeur à 4 cœurs, une seule fois) : une capture attend maintenant moins d'une seconde,
  et le coach affiche l'avancement de la préparation jusqu'à ce que les astuces proches de la vue apparaissent.

## [0.2.2] - 2026-11-12

### Ajouté

- Quand un composant système manque (`libgirepository-2.0-0` sur une Ubuntu 24.04 neuve), l'installateur l'installe
  d'un clic après avoir demandé votre mot de passe ; la commande à taper vous-même reste affichée.

### Corrigé

- L'installation du moteur n'échoue plus à l'étape du modèle d'IA (« No module named 'httpx' », 0.2.0 et 0.2.1).

## [0.2.1] - 2026-11-12

### Modifié

- GeoNesClick a sa propre icône (une épingle dans un réticule, sur des courbes de niveau) au lieu du logo de Tauri.

## [0.2.0] - 2026-11-12

### Ajouté

- **L'interface est en anglais et en français.** La langue se choisit sur le premier écran de l'installateur et peut
  être changée à tout moment dans Réglages › Général ; le changement s'applique tout de suite, et l'IA répond dans
  cette langue.
- L'espagnol, l'allemand, l'italien et le portugais traduisent toujours les astuces Plonk It ; leur interface est en
  anglais tant que leur traduction n'est pas ajoutée (un fichier par langue, `engine/src/geonesclick/locales/`).
- Quand l'installation du moteur échoue, l'installateur en nomme la cause : le site de téléchargement qui ne répond
  pas (GitHub, PyPI, PyTorch ou Hugging Face) ou un disque plein. Les téléchargements sont tentés 6 fois avant
  d'abandonner, et « Réessayer » garde ce qui est déjà téléchargé.

### Modifié

- **L'anglais est la langue par défaut.** Une installation existante passe en anglais : choisissez de nouveau le
  français dans Réglages › Général.
- « Relancer le partage », après que vous avez arrêté le partage d'écran depuis GNOME, rouvre le sélecteur de fenêtre
  au lieu de reprendre la fenêtre précédente (ce qui pouvait échouer avec « target not found »). Seul le démarrage de
  l'application reprend la fenêtre retenue sans demander.
- Le premier groupe de réglages s'appelle « Général » (niveau d'aide, langue, règle de preuve).
- Les consignes envoyées au modèle de vision sont en anglais, mesurées pour lire les panneaux aussi bien que les
  précédentes (accents compris) ; les textes du coach ne dépendent plus des mots qu'écrit le modèle.
- Votre fichier de métas est `~/.config/geonesclick/my-metas.toml` ; les indices d'amorce ont des identifiants
  stables, si bien que vos verdicts « Juste » / « Faux » survivent à un changement de langue.

### Corrigé

- La colonne des tailles de l'installateur ne passe plus à la ligne.

### Migration

Vos fichiers de la 0.1 sont convertis une fois, au premier démarrage de la 0.2.0, chacun avec une sauvegarde
`.before-0.2` à côté : `mes-metas.toml` devient `my-metas.toml` (vos verdicts sur l'amorce sont gardés), les noms de
catégories dans `config.toml` sont mis à jour, et le cache Plonk It est converti sur place (ses classements et
traductions par l'IA sont gardés). Une consigne de vision ou de marques que vous aviez personnalisée pour la 0.1 est
supprimée, parce qu'elle demandait l'ancien format de réponse : celle par défaut s'applique de nouveau. Un fichier qui
ne peut pas être converti est laissé tel quel et signalé dans les Réglages. Revenir à la 0.1.1 demande de restaurer
ces sauvegardes.

## [0.1.1] - 2026-11-08

### Corrigé

- Des textes de l'installateur et des réglages se sont révélés faux sur une Ubuntu 26.04 neuve sans carte NVIDIA (où va
  la mémoire de PLONK, où sont stockés le moteur et les modèles d'IA).
- L'avertissement de Hugging Face sur les requêtes non authentifiées n'apparaît plus dans le journal d'installation.

## [0.1.0] - 2026-11-08

Première version.

### Ajouté

- AppImage pour Ubuntu 24.04 ou plus récente avec GNOME, avec un installateur au premier lancement qui liste tout ce
  qu'il télécharge (quoi, d'où, taille, licence) avant le premier octet, puis installe le moteur dans
  `~/.local/share/geonesclick/`.
- Capture d'écran de la fenêtre du jeu (Super+Maj+G), aide par niveau de « Regarder » à « Réponse », pays probables
  selon StreetCLIP (local), ce que lit le modèle de vision distant, et les métas qui départagent les pays probables.
- Marques (Super+Maj+Z) : entourez un panneau, l'IA en recopie le texte, des règles locales concluent (alphabet,
  lettres, mots de rue, lieux GeoNames, distances sur les panneaux de direction).
- Verrous : dites au coach le pays, la région ou la ville dont vous êtes sûr.
- Onglet Carte avec les zones probables calculées localement (PLONK) et les lieux lus sur vos marques.
- Astuces Plonk It correspondant à la vue, traduites à la demande.
- « C'était où ? » après la manche, pour constituer un jeu de test et suivre vos progrès.
- Tous les réglages modifiables dans l'application ; « Tout effacer » supprime toutes vos données.

[Non publié]: https://github.com/MrNesClick/GeoNesClick/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/MrNesClick/GeoNesClick/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.5...v0.3.0
[0.2.5]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/MrNesClick/GeoNesClick/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/MrNesClick/GeoNesClick/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MrNesClick/GeoNesClick/releases/tag/v0.1.0
