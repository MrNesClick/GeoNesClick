// Description of the Settings screen: each editable engine setting (settings.py, EDITABLE) has its
// label, help, type and section here. The screen is built from this table.

export type Kind =
  | "bool"
  | "int"
  | "float"
  | "text"
  | "textarea"
  | "select"
  | "radio"
  | "rect" // [left, top, right, bottom] as fractions; empty = whole image
  | "rects" // list of rectangles, one per line
  | "categoryText" // one text value per metas category
  | "categoryNumber" // one number per category
  | "categoryList" // one list of words per category
  | "countries"; // candidate countries: tick, untick, add

export interface Field {
  section: string;
  key: string;
  label: string;
  hint?: string;
  kind: Kind;
  min?: number;
  max?: number;
  step?: number;
  options?: { value: string | number; label: string; hint?: string }[];
  /** Placed in the "Advanced" part of the section. */
  advanced?: boolean;
  /** Greyed out while this boolean setting is false. */
  needs?: [string, string];
}

export interface Group {
  id: string;
  title: string;
  /** Engine sections whose "file-only" part is shown in this group. */
  fileSections: string[];
  fields: Field[];
}

const LANGUAGES = [
  { value: "fr", label: "Français" },
  { value: "en", label: "Anglais (pas de traduction)" },
  { value: "es", label: "Espagnol" },
  { value: "de", label: "Allemand" },
  { value: "it", label: "Italien" },
  { value: "pt", label: "Portugais" },
];

export const GROUPS: Group[] = [
  {
    id: "aide",
    title: "Aide",
    fileSections: [],
    fields: [
      {
        section: "coach", key: "help_level", label: "Niveau d'aide", kind: "radio",
        hint: "Ce qui s'affiche tout seul après une capture (modifiable aussi en haut du coach).",
        options: [
          { value: 1, label: "1. Regarder", hint: "Où regarder, sans nommer de pays." },
          { value: 2, label: "2. Indices", hint: "Plus ce que voit l'IA, dont le texte lu." },
          { value: 3, label: "3. Pays", hint: "Plus les pays probables, la carte, les indices et les astuces." },
          { value: 4, label: "4. Réponse", hint: "Plus la synthèse en tête : pays, région, preuve." },
        ],
      },
      {
        section: "coach", key: "trust_proof", label: "Une preuve lue tranche", kind: "bool",
        hint: "Une preuve confirmée par une règle locale (mot, domaine, indicatif) met ce pays en tête, « certain », et écarte les autres. Une lecture de l'IA seule reste « très probable ».",
      },
      { section: "coach", key: "language", label: "Langue des traductions", kind: "select", options: LANGUAGES,
        hint: "L'interface du coach reste en français pour l'instant." },
      { section: "coach", key: "leader_min", label: "Probabilité minimale d'un pays donné en réponse", kind: "float",
        min: 0, max: 1, step: 0.05, advanced: true,
        hint: "Sans preuve lue : en dessous, le coach parle d'hésitation entre les premiers pays." },
      { section: "coach", key: "leader_margin", label: "Avance minimale sur le 2ᵉ pays", kind: "float", min: 0, max: 1,
        step: 0.05, advanced: true },
    ],
  },
  {
    id: "analyse",
    title: "Analyse",
    fileSections: ["streetclip", "vision"],
    fields: [
      { section: "streetclip", key: "enabled", label: "Analyse rapide en local (StreetCLIP)", kind: "bool",
        hint: "Pris en compte au prochain démarrage." },
      { section: "streetclip", key: "top_k", label: "Pays probables listés", kind: "int", min: 1, max: 20 },
      { section: "streetclip", key: "countries", label: "Pays candidats", kind: "countries",
        hint: "Décoche un pays pour l'écarter de l'analyse ; ajoute-en un par son nom anglais et son code ISO." },
      { section: "vision", key: "enabled", label: "Analyse approfondie (modèle de vision NVIDIA)", kind: "bool" },
      { section: "vision", key: "model", label: "Modèle de vision", kind: "text", needs: ["vision", "enabled"] },
      { section: "vision", key: "thinking", label: "Laisser le modèle raisonner (plus lent)", kind: "bool",
        needs: ["vision", "enabled"] },
      { section: "vision", key: "timeout_s", label: "Délai maximal (secondes)", kind: "float", min: 5, max: 300,
        needs: ["vision", "enabled"] },
      { section: "streetclip", key: "device", label: "Calcul de StreetCLIP", kind: "select", advanced: true,
        hint: "Pris en compte au prochain démarrage.",
        options: [{ value: "auto", label: "Automatique" }, { value: "cuda", label: "Carte graphique" },
                  { value: "cpu", label: "Processeur" }] },
      { section: "streetclip", key: "prompt", label: "Prompt de StreetCLIP", kind: "text", advanced: true,
        hint: "{} est remplacé par le nom anglais de chaque pays." },
      { section: "vision", key: "max_side_px", label: "Taille de l'image envoyée (px)", kind: "int", min: 256,
        max: 4096, advanced: true, hint: "Plus grand : le texte se lit mieux, la réponse arrive moins vite." },
      { section: "vision", key: "max_tokens", label: "Longueur maximale de la réponse (jetons)", kind: "int",
        min: 100, max: 16000, advanced: true },
      { section: "vision", key: "temperature", label: "Température", kind: "float", min: 0, max: 2, step: 0.1,
        advanced: true, hint: "0 : réponses les plus constantes." },
      { section: "vision", key: "prompt", label: "Prompt du modèle de vision", kind: "textarea", advanced: true },
    ],
  },
  {
    id: "indices",
    title: "Indices",
    fileSections: ["metas", "plonkit"],
    fields: [
      { section: "metas", key: "enabled", label: "Metas (indices par pays)", kind: "bool" },
      { section: "metas", key: "include_seed", label: "Utiliser l'amorce de metas (faits établis, non vérifiés)",
        kind: "bool", needs: ["metas", "enabled"] },
      { section: "metas", key: "judge_buttons", label: "Boutons « Juste » / « Faux » pour vérifier l'amorce",
        kind: "bool", needs: ["metas", "include_seed"] },
      { section: "metas", key: "show_looks", label: "Dire quoi observer avant de révéler les pays", kind: "bool",
        needs: ["metas", "enabled"] },
      { section: "metas", key: "max_categories", label: "Catégories « où regarder » affichées", kind: "int",
        min: 1, max: 12, needs: ["metas", "enabled"] },
      { section: "plonkit", key: "enabled", label: "Guides Plonk It", kind: "bool",
        hint: "Collectés sur ta machine pour ton usage, jamais redistribués." },
      { section: "plonkit", key: "similar_tips", label: "Montrer les astuces des pays candidats", kind: "bool",
        needs: ["plonkit", "enabled"] },
      { section: "plonkit", key: "similar_per_country", label: "Astuces par pays", kind: "int", min: 1, max: 5,
        needs: ["plonkit", "enabled"] },
      { section: "plonkit", key: "translate", label: "Traduire les astuces affichées", kind: "bool",
        needs: ["plonkit", "enabled"], hint: "À la demande, par le modèle NVIDIA ; gardées en cache." },
      { section: "plonkit", key: "pretranslate", label: "Traduire d'avance toute la base, en arrière-plan",
        kind: "bool", needs: ["plonkit", "translate"],
        hint: "Une fois pour toutes, après les manches en cours : les astuces s'affichent alors traduites tout de suite." },
      { section: "plonkit", key: "translate_timeout_s", label: "Délai maximal d'une traduction (s)", kind: "float",
        min: 5, max: 120, advanced: true, needs: ["plonkit", "translate"],
        hint: "Au-delà, les astuces de la manche restent en anglais." },
      { section: "plonkit", key: "ai_classify", label: "Faire classer par l'IA les astuces sans catégorie",
        kind: "bool", needs: ["plonkit", "enabled"] },
      { section: "plonkit", key: "refresh_days", label: "Vérifier les mises à jour (jours)", kind: "int", min: 1,
        max: 365, needs: ["plonkit", "enabled"] },
      { section: "metas", key: "min_probability", label: "Probabilité minimale d'un pays candidat", kind: "float",
        min: 0, max: 1, step: 0.01, advanced: true, hint: "Pays retenus pour le départage, au-dessus de ce seuil…" },
      { section: "metas", key: "max_candidates", label: "… et au plus ce nombre de pays", kind: "int", min: 2,
        max: 20, advanced: true },
      { section: "metas", key: "max_looks", label: "Consignes affichées par catégorie", kind: "int", min: 1, max: 5,
        advanced: true },
      { section: "metas", key: "category_looks", label: "Consigne « Regarde… » par catégorie", kind: "categoryText",
        advanced: true, hint: "Vide : consigne par défaut." },
      { section: "metas", key: "category_weights", label: "Poids de chaque catégorie dans le départage",
        kind: "categoryNumber", advanced: true, hint: "Vide : poids par défaut ; 0 : catégorie ignorée." },
      { section: "plonkit", key: "delay_s", label: "Pause entre deux pages collectées (s)", kind: "float", min: 1,
        max: 60, advanced: true },
      { section: "plonkit", key: "ai_model", label: "Modèle pour le classement et la traduction", kind: "text",
        advanced: true, hint: "Vide : le modèle de vision." },
      { section: "plonkit", key: "ai_batch", label: "Astuces par appel à l'IA", kind: "int", min: 5, max: 50,
        advanced: true },
      { section: "plonkit", key: "ai_pause_s", label: "Pause entre deux appels à l'IA (s)", kind: "float", min: 0,
        max: 60, advanced: true },
      { section: "plonkit", key: "keywords", label: "Mots-clés de classement des astuces (anglais)",
        kind: "categoryList", advanced: true, hint: "Séparés par des virgules ; vide : mots-clés par défaut." },
    ],
  },
  {
    id: "carte",
    title: "Carte",
    fileSections: ["map", "plonk"],
    fields: [
      { section: "map", key: "enabled", label: "Onglet Carte", kind: "bool",
        hint: "Fond OpenStreetMap en ligne : le serveur de tuiles voit ton adresse IP et les zones affichées." },
      { section: "plonk", key: "enabled", label: "Zones probables (PLONK, en local)", kind: "bool",
        hint: "Environ 120 Mo de mémoire vidéo. Une piste pour la carte, pas un vote sur le pays." },
      { section: "map", key: "max_zoom", label: "Zoom maximal", kind: "int", min: 2, max: 19,
        hint: "13 : les rues autour d'une position estimée par tes marques. Plus haut : plus de tuiles chargées en ligne.",
        needs: ["map", "enabled"] },
      { section: "plonk", key: "steps", label: "Pas du calcul", kind: "int", min: 10, max: 250, advanced: true,
        hint: "50 suffisent (mesuré) ; en dessous de 25, les zones se dégradent." },
      { section: "plonk", key: "points", label: "Positions tirées", kind: "int", min: 64, max: 2048, advanced: true },
      { section: "plonk", key: "zone_share", label: "Part des positions englobée par les zones", kind: "float",
        min: 0.25, max: 1, step: 0.05, advanced: true },
      { section: "plonk", key: "zone_link_km", label: "Distance de regroupement (km)", kind: "float", min: 20,
        max: 1000, advanced: true, hint: "Deux positions plus proches vont dans la même zone." },
      { section: "plonk", key: "zone_min_part", label: "Part minimale d'une zone", kind: "float", min: 0.01,
        max: 0.5, step: 0.01, advanced: true },
      { section: "map", key: "attribution", label: "Attribution du fond de carte", kind: "text", advanced: true },
      { section: "map", key: "tile_filter", label: "Filtre CSS des tuiles, de loin", kind: "text", advanced: true,
        hint: "Pays et zones. Vide : carte d'origine, sans assombrissement." },
      { section: "map", key: "close_zoom", label: "Zoom à partir duquel la carte s'éclaircit", kind: "int", min: 2,
        max: 19, needs: ["map", "enabled"],
        hint: "De près, la carte assombrie rend les villages et les routes illisibles." },
      { section: "map", key: "tile_filter_close", label: "Filtre CSS des tuiles, de près", kind: "text",
        advanced: true, hint: "Vide : carte d'origine." },
    ],
  },
  {
    id: "capture",
    title: "Capture",
    fileSections: ["capture"],
    fields: [
      { section: "capture", key: "notify", label: "Notification à chaque capture", kind: "bool" },
      { section: "capture", key: "sound", label: "Avec un son", kind: "bool", needs: ["capture", "notify"] },
      { section: "capture", key: "save_to_disk", label: "Garder une copie des captures sur le disque", kind: "bool" },
      { section: "capture", key: "keep_last", label: "Nombre de captures gardées (0 = toutes)", kind: "int", min: 0,
        needs: ["capture", "save_to_disk"] },
      { section: "capture", key: "source", label: "Ce que GNOME propose de partager", kind: "select", advanced: true,
        hint: "Pris en compte au prochain démarrage, ou avec « Changer de fenêtre ».",
        options: [{ value: "window", label: "Une fenêtre (recommandé)" }, { value: "monitor", label: "Un écran" },
                  { value: "both", label: "Les deux" }] },
      { section: "capture", key: "crop", label: "Zone analysée", kind: "rect", advanced: true,
        hint: "Fractions gauche, haut, droite, bas (ex. 0, 0.13, 1, 0.98) ; vide : image entière." },
      { section: "capture", key: "masks", label: "Zones masquées", kind: "rects", advanced: true,
        hint: "Un rectangle par ligne, en fractions de la zone analysée (ex. la mini-carte du jeu)." },
    ],
  },
  {
    id: "marques",
    title: "Marques",
    fileSections: ["rules"],
    fields: [
      { section: "marks", key: "enabled", label: "Marques (Super+Maj+Z ou « Marquer »)", kind: "bool",
        hint: "Fige la vue en plein écran : tu entoures chaque indice, l'IA recopie le texte de chacun." },
      { section: "marks", key: "max_marks", label: "Marques par vue figée", kind: "int", min: 1, max: 20,
        needs: ["marks", "enabled"] },
      { section: "marks", key: "upscale_to_px", label: "Agrandir les petites marques jusqu'à (px)", kind: "int",
        min: 64, max: 2048, needs: ["marks", "enabled"],
        hint: "Mesuré : un panneau de 140 px est lu déformé tel quel, exact une fois agrandi ×3 (420 px)." },
      { section: "marks", key: "max_upscale", label: "Agrandissement maximal", kind: "float", min: 1, max: 8, step: 0.5,
        needs: ["marks", "enabled"] },
      { section: "rules", key: "scripts", label: "L'alphabet écarte les pays qui ne l'écrivent pas", kind: "bool",
        hint: "Du cyrillique dans une marque exclut la France, même si l'IA a « lu » du français sur la vue entière." },
      { section: "rules", key: "letters", label: "Lettres et mots de rue propres à une langue", kind: "bool",
        hint: "« ъ » devant une consonne : bulgare ; « ő » : hongrois ; « utca » : hongrois. Pays très probable." },
      { section: "rules", key: "places", label: "Noms de villes et villages (GeoNames)", kind: "bool",
        hint: "Téléchargé une fois (~11 Mo, CC BY 4.0). Certain s'il est confirmé par une autre preuve et qu'aucune marque ne le contredit." },
      { section: "rules", key: "detail", label: "Villages du pays en tête (répertoire complet)", kind: "bool",
        needs: ["rules", "places"],
        hint: "Téléchargé une fois par pays (France 7,3 Mo) : trouve les petits villages (Laàs, L'Hôpital-d'Orion). GeoNames voit quel pays est consulté." },
      { section: "rules", key: "place_max_spread_km", label: "Écart maximal entre lieux d'une manche (km)", kind: "float",
        min: 50, max: 3000, advanced: true, needs: ["rules", "places"],
        hint: "Un homonyme plus loin des autres lieux lus est ignoré (« LAAS » → Lasa, en Italie)." },
      { section: "rules", key: "prior_min", label: "Un lieu seul est confirmé si StreetCLIP donne son pays à", kind: "float",
        min: 0, max: 1, step: 0.05, advanced: true, needs: ["rules", "places"],
        hint: "Sinon il faut un 2ᵉ lieu voisin, ou une lettre ou un mot de la langue du pays. Mesuré : 4 lieux seuls faux en un jour." },
      { section: "rules", key: "place_min_len", label: "Longueur minimale d'un nom de lieu", kind: "int", min: 3, max: 20,
        advanced: true, needs: ["rules", "places"], hint: "Plus court : ignoré (sigles, mots courants)." },
      { section: "marks", key: "parallel", label: "Lectures simultanées", kind: "int", min: 1, max: 8, advanced: true,
        hint: "Plus : les marques arrivent plus vite, au risque de dépasser les limites de l'API." },
      { section: "marks", key: "model", label: "Modèle de lecture des marques", kind: "text", advanced: true,
        hint: "Vide : le modèle de vision." },
      { section: "marks", key: "max_tokens", label: "Longueur maximale d'une lecture (jetons)", kind: "int", min: 50,
        max: 4000, advanced: true },
      { section: "marks", key: "prompt", label: "Prompt de lecture des marques", kind: "textarea", advanced: true,
        hint: "Le modèle recopie seulement : c'est le coach qui conclura." },
    ],
  },
  {
    id: "verrous",
    title: "Ce qui est sûr",
    fileSections: [],
    fields: [
      { section: "locks", key: "enabled", label: "« Tu sais où tu es ? » : pays › région › ville sûrs", kind: "bool",
        hint: "En tête du coach : ce qui est sûr restreint la recherche suivante. Tu le dis au coach, ou il le fixe seul quand c'est certain ; ✕ pour dire « pas ça ». Dure une capture." },
      { section: "locks", key: "auto_country", label: "Le coach fixe seul le pays quand tes marques le rendent certain",
        kind: "bool", needs: ["locks", "enabled"], hint: "Jamais sur « très probable »." },
      { section: "locks", key: "auto_region", label: "… et la région quand la position est nette ou que 2 lieux lus concordent", kind: "bool",
        needs: ["locks", "enabled"],
        hint: "Panneau aux distances cohérentes, et tous les lieux autour du point dans la même région." },
      { section: "locks", key: "propose_city", label: "Le coach propose une ville (« Oui » pour la retenir)",
        kind: "bool", needs: ["locks", "enabled"],
        hint: "Jamais verrouillée seule : un panneau « Pau 40 km » nomme un lieu où tu n'es pas." },
      { section: "locks", key: "region_radius_km", label: "Rayon autour du point pour la région (km)", kind: "float",
        min: 1, max: 100, advanced: true, needs: ["locks", "auto_region"],
        hint: "Tous les lieux à cette distance du point doivent être de la même région." },
      { section: "locks", key: "region_places_km", label: "Sans distance lue : écart maximal entre 2 lieux de la région (km)",
        kind: "float", min: 5, max: 300, advanced: true, needs: ["locks", "auto_region"],
        hint: "Au moins deux lieux lus dans la même région, à moins de cette distance : la région est fixée." },
    ],
  },
  {
    id: "jeu-de-test",
    title: "Jeu de test",
    fileSections: ["dataset"],
    fields: [
      { section: "dataset", key: "enabled", label: "« C'était où ? » après la manche", kind: "bool",
        hint: "La capture et le pays réel rejoignent le jeu de test, qui sert à mesurer le coach." },
      { section: "dataset", key: "ask_guessed", label: "Demander le pays que j'avais répondu", kind: "bool",
        needs: ["dataset", "enabled"], hint: "Sinon, un simple « Tu l'avais trouvé ? » Oui / Non." },
      { section: "dataset", key: "max_confusions", label: "Confusions affichées (0 = aucune)", kind: "int", min: 0,
        max: 10, needs: ["dataset", "ask_guessed"] },
    ],
  },
];

/** Storage: sizes, limit of the caches that grow, "Empty" buttons (StoragePanel). */
GROUPS.push({
  id: "stockage",
  title: "Stockage",
  fileSections: [],
  fields: [
    { section: "storage", key: "max_cache_mb", label: "Taille maximale des caches qui grossissent (Mo)", kind: "int",
      min: 50, max: 100000,
      hint: "Villages des pays rencontrés (plus tard : rues et recherches de rues). Le socle ne part jamais tout seul." },
  ],
});

/** Group without an editable setting: the engine's server, file-only. */
GROUPS.push({
  id: "moteur",
  title: "Moteur",
  fileSections: ["server"],
  fields: [
    { section: "debug", key: "enabled", label: "Mode débogage", kind: "bool",
      hint: "Garde un journal de chaque analyse (pays, zones, ce que l'IA a lu) à côté de sa capture, pour relire une manche après coup." },
  ],
});

/** Labels of the file-only settings (settings.py, FILE_ONLY). */
export const FILE_ONLY_LABELS: Record<string, string> = {
  "server.host": "Adresse d'écoute du moteur",
  "server.port": "Port du moteur",
  "server.allowed_origins": "Origines autorisées",
  "capture.directory": "Dossier des captures",
  "dataset.directory": "Dossier du jeu de test",
  "metas.user_file": "Fichier de tes metas",
  "plonkit.data_dir": "Dossier des guides Plonk It",
  "streetclip.model": "Modèle StreetCLIP",
  "streetclip.revision": "Version des poids StreetCLIP",
  "plonk.model": "Modèle PLONK",
  "plonk.revision": "Version des poids PLONK",
  "map.tile_url": "Serveur de tuiles",
  "map.attribution_url": "Lien de l'attribution",
  "vision.base_url": "Adresse de l'API de vision",
  "vision.api_key_env": "Variable de la clé API",
  "rules.places_url": "Source du répertoire de lieux",
  "rules.detail_url": "Source du détail par pays",
  "rules.regions_url": "Source des noms de régions",
  "rules.places_dir": "Dossier du répertoire de lieux",
};
