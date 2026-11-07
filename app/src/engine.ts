// Connexion au moteur Python : WebSocket pour les résultats poussés, HTTP pour les commandes.
import { reactive } from "vue";
import { openUrl } from "@tauri-apps/plugin-opener";

const ENGINE_URL: string = import.meta.env.VITE_ENGINE_URL ?? "http://127.0.0.1:47615";
const WS_URL = ENGINE_URL.replace(/^http/, "ws") + "/ws";

export interface CountryScore {
  name: string;
  code: string;
  probability: number;
}

export interface Hint {
  hint: string;
  countries: string[];
  source: string;
  verified: boolean;
}

/** Une catégorie à regarder pour départager les pays candidats. */
export interface LookFor {
  category: string;
  label: string;
  score: number;
  /** Quoi observer pour trancher, sans nommer de pays. */
  looks: string[];
  hints: Hint[];
}

/** Une astuce Plonk It dont le texte ressemble à la vue (comparaison CLIP, en local). */
export interface SimilarTip {
  /** Empreinte du texte : clé de la traduction. */
  id: string;
  text: string;
  /** Traduction dans la langue du coach, si elle est déjà connue. */
  translated: string | null;
  section: string;
  category: string;
  url: string;
  score: number;
}

/** Un pays réel souvent pris pour un autre, avec les metas qui les séparent. */
export interface Confusion {
  country: string;
  guessed: string;
  count: number;
  lookfor: LookFor[];
}

export interface Progress {
  rounds: number;
  found: number;
  by_country: Record<string, [number, number]>;
  model_top1: number;
  model_rounds: number;
  confusions: Confusion[];
}

export type Fiche = Record<string, unknown>;

/** Conclusion du modèle de vision, seulement sur preuve explicite (texte lu, domaine, drapeau, plaque). */
export interface Conclusion {
  country: string;
  region: string;
  proof: string;
  certainty: string;
}

/** Lit la clé « conclusion » de la fiche ; null si absente, vide ou pays inconnu de la configuration. */
export function conclusionOf(fiche: Fiche): Conclusion | null {
  const c = fiche.conclusion;
  if (!c || typeof c !== "object") return null;
  const field = (key: string) => {
    const v = (c as Record<string, unknown>)[key];
    return typeof v === "string" ? v.trim() : "";
  };
  const country = field("pays").toUpperCase();
  if (!engine.countries.includes(country)) return null;
  return { country, region: field("region"), proof: field("preuve"), certainty: field("certitude").toLowerCase() };
}

/** Preuve lue par l'IA pour cette capture (null tant que l'IA n'a pas répondu, ou sans preuve). */
export const proofOf = (a: Analysis): Conclusion | null =>
  a.vision.status === "done" ? conclusionOf(a.vision.fiche) : null;

/** Preuve de certitude forte, quand le réglage « une preuve lue tranche » est actif. */
export function certainProof(a: Analysis): Conclusion | null {
  const proof = proofOf(a);
  return engine.trustProof && proof?.certainty === "forte" ? proof : null;
}

/** Astuces Plonk It à afficher, dans l'ordre des pays probables (seul le pays prouvé si la preuve est forte). */
export function tipsByCountry(a: Analysis): { code: string; tips: SimilarTip[] }[] {
  const certain = certainProof(a);
  return (a.scores ?? [])
    .filter((s) => !certain || s.code === certain.country)
    .map((s) => ({ code: s.code, tips: a.similar?.[s.code] ?? [] }))
    .filter((c) => c.tips.length);
}

/** Zone où la vue se trouve probablement : contour arrondi autour des positions PLONK les plus denses. */
export interface Zone {
  /** Contour [latitude, longitude] en degrés. */
  polygon: [number, number][];
  /** Part des positions du nuage dans cette zone (0 à 1). */
  part: number;
  width_km: number;
  height_km: number;
  /** Pays principaux de la zone et leur part dans la zone (au plus deux). */
  countries: [string, number][];
}

/** Nuage PLONK de la vue, résumé en zones par le moteur (une piste pour la carte, jamais un vote de pays). */
export interface Cloud {
  zones: Zone[];
  /** Les mêmes zones calculées pays par pays (pays d'au moins 5 % des positions), pour suivre une preuve. */
  zones_by_country: Record<string, Zone[]>;
  ms: number;
}

/** Zones à dessiner : seules celles du pays prouvé quand la preuve est forte (les autres pays sont écartés). */
export function visibleZones(a: Analysis): Zone[] {
  if (a.cloud.status !== "done") return [];
  const certain = certainProof(a);
  return certain ? (a.cloud.data.zones_by_country[certain.country] ?? []) : a.cloud.data.zones;
}

export interface Analysis {
  id: string;
  at: string;
  /** Instant de réception de la capture (horloge locale), pour afficher le temps écoulé. */
  receivedAt: number;
  thumbnail: string;
  captureMs: number;
  scores: CountryScore[] | null;
  lookfor: LookFor[] | null;
  similar: Record<string, SimilarTip[]> | null;
  /** Traduction des astuces en cours (null : rien à traduire), ou message d'erreur. */
  translation: "pending" | "done" | string | null;
  clipMs: number | null;
  labelled: { country: string; guessed: string; found: boolean | null } | null;
  /** Nuage de la carte : off (PLONK désactivé ou absent), en cours, prêt, ou en échec. */
  cloud: { status: "off" } | { status: "pending" } | { status: "done"; data: Cloud } | { status: "error"; error: string };
  vision:
    | { status: "off" }
    | { status: "pending"; model: string }
    | { status: "done"; model: string; seconds: number; fiche: Fiche }
    | { status: "error"; error: string };
}

export const engine = reactive({
  connected: false,
  capture: { alive: false, starting: true, message: "connexion au moteur…" },
  streetclip: { ready: false, message: "" },
  vision: { enabled: false, ready: false, model: "" },
  metas: { count: 0, message: "", judge: true },
  dataset: { enabled: false, ask_guessed: true },
  plonkit: { enabled: false, status: "off", message: "", tips: 0 },
  plonk: { enabled: false, ready: false, message: "" },
  map: { enabled: false, tile_url: "", attribution: "", attribution_url: "", tile_filter: "", max_zoom: 10 },
  countries: [] as string[],
  /** Niveau d'aide : 1 où regarder, 2 + ce que voit l'IA, 3 + pays et indices, 4 + synthèse de la réponse. */
  helpLevel: 4,
  /** Une preuve lue avec certitude forte met son pays en tête et écarte les autres. */
  trustProof: true,
  busy: false,
  error: null as string | null,
  current: null as Analysis | null,
  progress: null as Progress | null,
});

type Message =
  | {
      type: "state";
      capture: typeof engine.capture;
      streetclip: typeof engine.streetclip;
      vision: typeof engine.vision;
      metas: typeof engine.metas;
      dataset: typeof engine.dataset;
      plonkit: typeof engine.plonkit;
      plonk: typeof engine.plonk;
      map: typeof engine.map;
      countries: string[];
      help_level: number;
      trust_proof: boolean;
    }
  | { type: "capture"; id: string; at: string; thumbnail: string; ms: number }
  | {
      type: "streetclip";
      id: string;
      ms: number;
      scores: CountryScore[];
      lookfor: LookFor[];
      similar: Record<string, SimilarTip[]>;
      translating: boolean;
      cloud: boolean;
    }
  | ({ type: "cloud"; id: string } & (Cloud | { error: string }))
  | { type: "tips_translated"; id: string; translations: Record<string, string>; error?: string }
  | { type: "vision_pending"; id: string; model: string }
  | { type: "vision"; id: string; model: string; seconds: number; fiche: Fiche }
  | { type: "vision_error"; id: string; error: string }
  | { type: "labelled"; id: string; country: string; guessed: string; found: boolean | null; progress: Progress }
  | { type: "lookfor"; id: string; lookfor: LookFor[] }
  | { type: "error"; message: string };

function handle(msg: Message) {
  const cur = engine.current;
  switch (msg.type) {
    case "state":
      engine.capture = msg.capture;
      engine.streetclip = msg.streetclip;
      engine.vision = msg.vision;
      engine.metas = msg.metas;
      engine.dataset = msg.dataset;
      engine.plonkit = msg.plonkit;
      engine.plonk = msg.plonk;
      engine.map = msg.map;
      engine.countries = msg.countries;
      engine.helpLevel = msg.help_level;
      engine.trustProof = msg.trust_proof;
      break;
    case "capture":
      engine.error = null;
      engine.current = {
        id: msg.id,
        at: msg.at,
        receivedAt: Date.now(),
        thumbnail: msg.thumbnail,
        captureMs: msg.ms,
        scores: null,
        lookfor: null,
        similar: null,
        translation: null,
        clipMs: null,
        labelled: null,
        cloud: { status: "off" },
        vision: engine.vision.enabled ? { status: "pending", model: engine.vision.model } : { status: "off" },
      };
      break;
    case "streetclip":
      if (cur?.id === msg.id) {
        cur.scores = msg.scores;
        cur.lookfor = msg.lookfor;
        cur.similar = msg.similar;
        cur.translation = msg.translating ? "pending" : null;
        cur.clipMs = msg.ms;
        cur.cloud = msg.cloud ? { status: "pending" } : { status: "off" };
      }
      break;
    case "cloud":
      if (cur?.id === msg.id) {
        cur.cloud = "error" in msg ? { status: "error", error: msg.error } : { status: "done", data: msg };
      }
      break;
    case "tips_translated":
      if (cur?.id === msg.id && cur.similar) {
        const all = Object.values(cur.similar).flat();
        for (const tip of all) tip.translated = msg.translations[tip.id] ?? tip.translated;
        // Les lots arrivent un par un : « en cours » tant qu'il reste une astuce sans traduction.
        if (msg.error) cur.translation = msg.error;
        else if (all.every((tip) => tip.translated)) cur.translation = "done";
      }
      break;
    case "lookfor": // recalculé après un verdict « Juste » / « Faux »
      if (cur?.id === msg.id) cur.lookfor = msg.lookfor;
      break;
    case "vision_pending":
      if (cur?.id === msg.id) cur.vision = { status: "pending", model: msg.model };
      break;
    case "vision":
      if (cur?.id === msg.id) cur.vision = { status: "done", model: msg.model, seconds: msg.seconds, fiche: msg.fiche };
      break;
    case "vision_error":
      if (cur?.id === msg.id) cur.vision = { status: "error", error: msg.error };
      break;
    case "labelled":
      if (cur?.id === msg.id) cur.labelled = { country: msg.country, guessed: msg.guessed, found: msg.found };
      engine.progress = msg.progress;
      break;
    case "error":
      engine.error = msg.message;
      break;
  }
}

export function connect() {
  const ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    engine.connected = true;
    void loadProgress();
  };
  ws.onmessage = (event) => handle(JSON.parse(event.data) as Message);
  ws.onclose = () => {
    engine.connected = false;
    setTimeout(connect, 1500); // le moteur démarre en quelques secondes
  };
}

async function request(path: string, body?: unknown): Promise<Response | null> {
  engine.busy = true;
  try {
    const res = await fetch(ENGINE_URL + path, {
      method: "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().then((j) => j.detail ?? j.error).catch(() => null);
      engine.error = typeof detail === "string" ? `Refusé par le moteur : ${detail}.` : `Le moteur a répondu ${res.status}.`;
    }
    return res;
  } catch {
    engine.error = "Le moteur ne répond pas.";
    return null;
  } finally {
    engine.busy = false;
  }
}

async function loadProgress() {
  try {
    const res = await fetch(ENGINE_URL + "/progress");
    if (res.ok) engine.progress = (await res.json()) as Progress;
  } catch {
    /* sans importance : la progression arrivera avec la prochaine étiquette */
  }
}

export const requestCapture = () => request("/capture");
export const restartSharing = () => request("/capture/restart");
export const reselectWindow = () => request("/capture/reselect");
/** « C'était où ? » : pays réel, et pays répondu (vide si tu ne sais plus) ou simple « trouvé ? ». */
export const labelCapture = (id: string, country: string, guessed: string, found: boolean | null = null) =>
  request("/label", { id, country, guessed, found });
export const refreshPlonkit = () => request("/plonkit/refresh");

/** Change le niveau d'aide tout de suite, puis l'enregistre dans config.toml. */
export async function setHelpLevel(level: number) {
  engine.helpLevel = level;
  await saveSettings({ coach: { help_level: level } });
}

/** Libellés des catégories de metas (mêmes clés que metas.py). */
export const CATEGORY_LABELS: Record<string, string> = {
  langue: "Langue et alphabet",
  conduite: "Sens de circulation",
  marquage: "Marquage au sol",
  poteaux: "Poteaux",
  bornes: "Bornes et délinéateurs",
  plaques: "Plaques d'immatriculation",
  panneaux: "Panneaux",
  domaine: "Noms de domaine",
  voiture: "Voiture et caméra Google",
  vegetation: "Végétation et sol",
  architecture: "Architecture",
  autre: "Autres indices",
};
/** Ouvre une page Plonk It dans le navigateur (seules ces adresses sont autorisées par Tauri). */
export async function openPlonkit(url: string) {
  if (!url.startsWith("https://www.plonkit.net/")) return;
  try {
    await openUrl(url);
  } catch {
    engine.error = "Impossible d'ouvrir le navigateur.";
  }
}

/** Texte Markdown d'une astuce en segments (gras ou non), sans jamais interpréter de HTML. */
export function markdownSegments(md: string): { text: string; bold: boolean }[] {
  const plain = md.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[_`#>]/g, "");
  return plain.split("**").map((text, i) => ({ text, bold: i % 2 === 1 })).filter((s) => s.text);
}

/** Verdict du joueur sur un indice de l'amorce ; le moteur l'écrit dans mes-metas.toml. */
export const judgeHint = (category: string, hint: string, verdict: "right" | "wrong") =>
  request("/metas/judge", { category, hint, verdict, id: engine.current?.id ?? "" });

/** Contours des pays (Natural Earth, servis par le moteur), chargés une seule fois. */
let outlines: Promise<GeoJSON.FeatureCollection | null> | null = null;
export function countryOutlines(): Promise<GeoJSON.FeatureCollection | null> {
  outlines ??= getJSON<GeoJSON.FeatureCollection>("/map/countries").then((g) => {
    if (!g) outlines = null; // moteur pas encore prêt : on réessaiera à la prochaine carte
    return g;
  });
  return outlines;
}

/** Ouvre la page d'attribution du fond de carte (seule l'adresse OpenStreetMap est autorisée par Tauri). */
export async function openAttribution() {
  const url = engine.map.attribution_url;
  if (!url.startsWith("https://")) return;
  try {
    await openUrl(url);
  } catch {
    engine.error = "Impossible d'ouvrir le navigateur.";
  }
}

// --- Pays : noms français et drapeaux ------------------------------------------------------------
const regionNames = new Intl.DisplayNames(["fr"], { type: "region" });
export const countryName = (code: string) => regionNames.of(code) ?? code;
/** Nombre à la française : « 13,2 ». */
export const fr = (n: number) => n.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
export const flag = (code: string) =>
  String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));

// --- Réglages ------------------------------------------------------------------------------------
export type Settings = Record<string, Record<string, string | number | boolean>>;

export async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(ENGINE_URL + path);
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export async function saveSettings(settings: Settings): Promise<string | null> {
  const res = await request("/settings", settings);
  if (res?.ok) {
    engine.error = null;
    return null;
  }
  return engine.error ?? "Enregistrement impossible.";
}

/** Test d'un modèle : appel séparé, pour ne pas bloquer la capture pendant ces quelques secondes. */
export async function testModel(model: string): Promise<{ ok: boolean; seconds?: number; error?: string }> {
  try {
    const res = await fetch(ENGINE_URL + "/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    });
    if (res.ok) return await res.json();
    return { ok: false, error: res.status === 422 ? "Identifiant de modèle invalide." : `Le moteur a répondu ${res.status}.` };
  } catch {
    return { ok: false, error: "Le moteur ne répond pas." };
  }
}
