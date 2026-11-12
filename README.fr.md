[English](README.md) | **Français**

# GeoNesClick

Coach de géolocalisation assisté par IA, pour s'entraîner à l'OSINT et à GeoGuessr. Appuie sur un raccourci pendant
une manche : le coach regarde la vue affichée à l'écran et te guide vers les indices utiles, avec autant d'aide que
tu le souhaites.

> **Pour l'entraînement uniquement.** Le coach ne lit que l'image affichée, jamais les données du jeu. Les
> [règles de la communauté](https://www.geoguessr.com/community-rules) de GeoGuessr comptent comme triche tout outil
> tiers qui donne un avantage injuste : ne l'utilise jamais en multijoueur ou en compétition, ni partout où ton score
> est comparé à celui des autres.

## Fonctionnalités

- **Quatre niveaux d'aide**, de « où regarder » à la réponse complète avec sa preuve.
- **IA locale** (StreetCLIP) pour les pays probables, en 60 ms environ avec une carte NVIDIA (1,6 s sur un
  processeur à 4 cœurs), plus un modèle de vision distant qui lit le texte de la vue.
- **Marques** : encadre un panneau ou une enseigne ; le coach le lit et en tire des conclusions locales et sourcées.
- **Carte** des zones probables (PLONK, calculé en local) et des lieux lus sur tes panneaux.
- **Suivi de ta progression** : après chaque manche, « C'était où ? » enregistre le pays réel et montre tes
  confusions.
- Tout se règle dans l'app, et tout ce qu'elle télécharge est annoncé avant le premier octet.

L'interface existe en anglais et en français (au choix dès le premier lancement, modifiable dans les Réglages).

## Prérequis

- Linux 64 bits avec GNOME (Wayland ou Xorg) et une glibc 2.39 ou plus récente.
  - **Validé sur** : Ubuntu 24.04, Ubuntu 26.04.
  - Les autres distributions avec GNOME et une glibc 2.39 ou plus récente (Debian 13, Fedora 40 ou plus récent…) ne
    sont pas encore validées mais devraient marcher : [dis-nous ce qu'il en est][retour] ; un retour où tout marche
    ajoute ton système à cette liste ([détail des retours](docs/compatibility.md), en anglais).
- Environ 11 Go d'espace disque libre pendant l'installation, 8 Go occupés ensuite (environ 3 Go sans carte NVIDIA)
- 8 Go de mémoire vive (sans carte NVIDIA, le moteur seul en occupe environ 2,5 Go)
- Une carte NVIDIA (recommandée ; sans elle, l'IA locale tourne sur le processeur, plus lentement)
- Une clé API NVIDIA gratuite sur [build.nvidia.com](https://build.nvidia.com) (recommandée : elle lit le texte de
  la vue et traduit les astuces)

## Installer

1. Télécharge `GeoNesClick_<version>_amd64.AppImage` depuis la page
   [Releases](https://github.com/MrNesClick/GeoNesClick/releases).
2. Rends-la exécutable (clic droit › Propriétés › *Exécutable comme programme*, ou
   `chmod +x GeoNesClick_*.AppImage`), puis ouvre-la.
3. Au premier lancement, un assistant vérifie ton système et installe un composant manquant en un clic, avec ton
   mot de passe (apt, dnf, pacman ou zypper). Il liste ensuite tout ce qu'il va télécharger, avec la taille et la
   licence de chaque élément. Une fois ton accord donné, il installe le moteur dans `~/.local/share/geonesclick/` et
   les modèles d'IA dans `~/.cache/huggingface/` ; rien d'autre n'entre dans le système. Le téléchargement passe par
   GitHub, PyPI, Hugging Face et, sans carte NVIDIA, PyTorch : si l'un d'eux ne répond pas, l'assistant le nomme.
   Réessaie plus tard : ce qui est déjà téléchargé est gardé.
4. Choisis tes options, saisis ta clé API si tu en as une, et c'est prêt.

Pour mettre à jour, télécharge la nouvelle AppImage et ouvre-la : l'assistant met le moteur à jour.

## Utiliser

1. Ouvre une partie GeoGuessr dans ton navigateur et lance GeoNesClick. La première fois, GNOME demande quelle
   fenêtre partager : choisis celle du navigateur.
2. Pendant une manche, appuie sur **Super+Maj+G** : le coach affiche l'aide du niveau choisi.
3. Pour lire un panneau, appuie sur **Super+Maj+Z** et encadre-le.

## Niveaux d'aide

| Niveau | Ce qui s'affiche |
|---|---|
| 1. Regarder | où regarder, sans nommer de pays |
| 2. Indices | + ce que voit l'IA, dont le texte lu mot pour mot |
| 3. Pays | + pays probables, carte, astuces Plonk It |
| 4. Réponse (défaut) | + la réponse : pays, région si un texte la nomme, et la preuve |

## Ce que GeoNesClick télécharge

Chaque accès réseau est listé dans [`downloads.toml`](engine/src/geonesclick/downloads.toml) et affiché par l'app
avant tout téléchargement. Les options se coupent dans les Réglages.

| Quoi | D'où | Taille | Licence | Quand | Ce qui part de ta machine |
|---|---|---|---|---|---|
| Python 3.12 **(obligatoire)** | `github.com`, `objects.githubusercontent.com` | 30 Mo | PSF-2.0 | une fois, à l'installation | — |
| Bibliothèques Python (PyTorch, Transformers, FastAPI…) **(obligatoire)** | `pypi.org`, `files.pythonhosted.org` | 3,1 Go avec une carte NVIDIA, 70 Mo sans | variées (BSD, MIT, Apache-2.0…) | une fois, à l'installation | — |
| PyTorch pour processeur, sans carte NVIDIA **(obligatoire)** | `download.pytorch.org` | 200 Mo | BSD-3-Clause | une fois, à l'installation | — |
| Modèle StreetCLIP **(obligatoire)** | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 1,7 Go | CC BY-NC 4.0 (non commercial) | une fois, à l'installation | — |
| Répertoire des lieux GeoNames et noms des régions | `download.geonames.org` | 11 Mo | CC BY 4.0 | une fois, si tu l'acceptes | — |
| Villages du pays en tête (GeoNames) | `download.geonames.org` | 8 Mo | CC BY 4.0 | à la demande | — |
| Guides Plonk It | `www.plonkit.net` | 2 Mo | pour ton usage personnel, jamais redistribués | si tu l'acceptes : une fois, puis les guides modifiés tous les 30 jours | — |
| Modèle PLONK | `huggingface.co`, `cas-bridge.xethub.hf.co`, `cdn-lfs.hf.co` | 144 Mo | MIT | une fois, si tu l'acceptes | — |
| Modèle de vision NVIDIA (API en ligne) | `integrate.api.nvidia.com` | — | conditions de l'API NVIDIA ; ta clé | à chaque usage | tes captures (réduites à 1 280 px), les découpes de tes marques, les astuces Plonk It à classer et à traduire |
| Tuiles de carte OpenStreetMap | `tile.openstreetmap.org` | — | ODbL ; politique des tuiles de l'OSMF | à chaque usage | ton adresse IP et les zones de carte affichées |

## Confidentialité

- Le moteur tourne sur ta machine et ne répond qu'à la fenêtre du coach : aucun site web ni autre ordinateur ne
  peut le joindre.
- Tes captures ne quittent ta machine que vers le modèle de vision NVIDIA, et seulement si tu as donné une clé API
  (voir le tableau ci-dessus).
- Ta clé API est rangée dans un fichier lisible par toi seul.
- Réglages › Stockage › **Tout effacer** supprime toutes tes données, et le moteur si tu le souhaites.

## Documentation

La documentation détaillée est en anglais :

- [How it works](docs/how-it-works.md) : la carte Réponse, marques, règles locales, ce qui est sûr, metas, Plonk It,
  carte
- [Architecture](docs/architecture.md) : les parties Rust, Vue et Python, et comment elles se parlent
- [Configuration](docs/configuration.md) : `config.toml`, réglages, mode débogage
- [Measurements and benchmarks](docs/benchmarks.md) : pourquoi chaque choix technique, et les tests
- [Maintenance](docs/maintenance.md) : mises à jour, emplacement des données, outils et licences
- [Development](docs/development.md) : compiler depuis les sources, fabriquer l'AppImage, lancer les tests
- [Compatibility](docs/compatibility.md) : ce qu'il faut à GeoNesClick, les systèmes testés et signalés
- [Changelog](CHANGELOG.md) : ce qui change d'une version à l'autre (en anglais)
- [Contributing](CONTRIBUTING.md) et [Security](SECURITY.md) : comment contribuer, comment signaler une faille

## Licence

Code sous licence [Apache-2.0](LICENSE) © 2026 MrNesClick. Le modèle StreetCLIP est sous **CC BY-NC 4.0** : aucun
usage commercial du coach.

[retour]: https://github.com/MrNesClick/GeoNesClick/issues/new?template=system-report.yml
