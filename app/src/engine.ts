// Connexion au moteur Python : WebSocket pour les résultats poussés, HTTP pour les commandes.
import { reactive } from "vue";
import { openUrl } from "@tauri-apps/plugin-opener";

export const ENGINE_URL: string = import.meta.env.VITE_ENGINE_URL ?? "http://127.0.0.1:47615";
export const WS_URL = ENGINE_URL.replace(/^http/, "ws") + "/ws";

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

/** Conclusion : celle des règles locales sur tes marques, sinon celle du modèle de vision (vue entière). */
export interface Conclusion {
  /** marks : règles locales sur le texte de tes marques ; vision : lecture de la vue entière par l'IA. */
  source: "marks" | "vision";
  country: string;
  region: string;
  proof: string;
  certainty: string;
  /** Confirmée par une règle locale (mot, domaine, indicatif…). Mesuré : le modèle seul se trompe parfois
   * avec « certitude forte » (Slovaquie sur « utca » mal lu) ; sans confirmation, jamais « certain ». */
  confirmed: boolean;
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
  return {
    source: "vision", country, region: field("region"), proof: field("preuve"),
    certainty: field("certitude").toLowerCase(),
    confirmed: false, // l'IA seule n'est jamais « certaine » : seules les règles locales confirment
  };
}

/** Une preuve tirée d'une marque par une règle locale. */
export interface Evidence {
  kind: "alphabet" | "lettres" | "mot" | "lieu" | "rue";
  value: string;
  label: string;
  countries: string[];
  source: string;
  /** Pourquoi elle ne compte pas (« hors de tes pays candidats ») ; vide sinon. */
  note?: string;
  /** Lieu : homonymes retenus [latitude, longitude, pays, nom GeoNames, région]. */
  points?: [number, number, string, string, string?][];
}

/** Un verrou : ce qui est fixé pour la capture (pays › région › ville), par le coach ou par toi. */
export interface Lock {
  level: "country" | "region" | "city";
  country: string;
  /** Code GeoNames de la région (« FR.75 ») : région, et ville si on la connaît. */
  region: string;
  /** Nom de la région ou de la ville (le pays : countryName). */
  name: string;
  lat: number | null;
  lon: number | null;
  by: "coach" | "user";
  /** Ce qui l'a fait poser par le coach (« marques 1, 2 »). */
  why: string;
}

export interface Locks {
  held: Partial<Record<Lock["level"], Lock>>;
  /** Rejetés pour toute la capture : le coach ne les reverrouille pas. */
  rejected: Lock[];
  /** Ville proposée par le coach : jamais verrouillée sans toi. */
  proposal: Lock | null;
  /** Régions des lieux lus dans tes marques, proposées en un clic (plusieurs : à toi de trancher). */
  read_regions: { code: string; name: string; marks: number[]; places: string[] }[];
  /** Étendue de la région choisie [sud, ouest, nord, est], d'après ses lieux GeoNames (pas de contour). */
  region_bounds: [number, number, number, number] | null;
}

/** Résultat de la recherche du « + » (index GeoNames local). */
export interface PlaceFound {
  name: string;
  code?: string;
  country?: string;
  region?: string;
  region_name?: string;
  lat?: number;
  lon?: number;
  population?: number;
}

/** Pays verrouillé (par toi ou par le coach), ou null. */
export const lockedCountry = (a: Analysis): string | null => a.locks?.held.country?.country ?? null;

/** Ce que les marques prouvent ensemble (règles locales du moteur, evidence.py). */
export interface Verdict {
  country: string;
  /** certain (lieu + autre preuve, aucune marque contraire), probable (très probable), ou "" */
  level: "certain" | "probable" | "";
  /** Pays que l'alphabet laisse possibles ; null : aucun écarté. */
  allowed: string[] | null;
  scripts: string[];
  cites: { n: number; items: string[] }[];
  against: { n: number; country: string; items: string[] }[];
  conflict: string;
  /** Position estimée d'après les lieux lus (et les distances d'un panneau), null sans lieu. */
  location: Location | null;
  /** Homonymes lointains écartés (« LAAS » → Lasa, Italie, loin des autres lieux lus) : ne comptent pas. */
  ignored: { n: number; value: string; label: string; countries: string[] }[];
  /** Lieux seuls, sans confirmation (2ᵉ lieu, lettre ou mot, StreetCLIP) : de simples indices. */
  unconfirmed: { n: number; value: string; country: string }[];
  /** Lieux lus que tes choix écartent (hors de ton pays ou de ta région) : grisés sur la carte. */
  outside?: { n: number; name: string; label: string; lat: number; lon: number }[];
}

/** Un lieu lu sur une marque, placé sur la carte (GeoNames). */
export interface PlaceRead {
  n: number;
  name: string;
  label: string;
  km: number | null;
  lat: number;
  lon: number;
}

/** point : triangulée (plusieurs distances) ; ring : à une distance d'un lieu ; places : dans les parages des lieux. */
export type Location =
  | { kind: "point"; lat: number; lon: number; radius_km: number; places: PlaceRead[] }
  | { kind: "ring"; lat: number; lon: number; radius_km: number; spread_km: number; places: PlaceRead[] }
  | { kind: "places"; places: PlaceRead[] }
  /** Distances incohérentes (chiffre mal lu) : au plus radius_km du lieu le plus proche, toujours vrai. */
  | { kind: "rough"; lat: number; lon: number; radius_km: number; doubtful: { n: number; name: string; km: number }[];
      places: PlaceRead[] };

/** Pays écarté par l'alphabet de tes marques (« cyrillique » exclut la France). */
export const excluded = (a: Analysis, code: string): boolean =>
  !!a.verdict?.allowed && !a.verdict.allowed.includes(code);

/** Conclusion des règles locales sur tes marques, citant les marques qui la prouvent. */
export function marksConclusion(a: Analysis): Conclusion | null {
  const v = a.verdict;
  if (!v?.country || !v.level) return null;
  return {
    source: "marks", country: v.country, region: "",
    proof: v.cites.map((c) => `${circled(c.n)} ${c.items.join(", ")}`).join(" · "),
    certainty: v.level === "certain" ? "forte" : "moyenne", confirmed: v.level === "certain",
  };
}

/** Conclusion de l'IA sur la vue entière que l'alphabet de tes marques contredit (France sur du cyrillique). */
export function rejectedVision(a: Analysis): Conclusion | null {
  const c = a.vision.status === "done" ? conclusionOf(a.vision.fiche) : null;
  return c && excluded(a, c.country) ? c : null;
}

/** La preuve qui compte : tes marques d'abord ; sinon la lecture de l'IA, si l'alphabet ne l'exclut pas. */
export function proofOf(a: Analysis): Conclusion | null {
  const marks = marksConclusion(a);
  if (marks) return marks;
  const vision = a.vision.status === "done" ? conclusionOf(a.vision.fiche) : null;
  return vision && !excluded(a, vision.country) ? vision : null;
}

/** Libellé d'une preuve selon sa source et sa confirmation. */
export function proofLabel(c: Conclusion): string {
  if (c.source === "marks") return c.confirmed ? "Certain : lu dans tes marques" : "Très probable : lu dans tes marques";
  return c.certainty === "forte" ? "Très probable : lu par l'IA, à confirmer" : "Probable : lu par l'IA, à confirmer";
}

/** Preuve CERTAINE : forte, confirmée par une règle locale, et réglage « une preuve lue tranche » actif. */
export function certainProof(a: Analysis): Conclusion | null {
  const proof = proofOf(a);
  return engine.trustProof && proof?.certainty === "forte" && proof.confirmed ? proof : null;
}

/** Pays qui se détache nettement d'après StreetCLIP, ou null : le coach parle alors d'hésitation. */
/** Pays de StreetCLIP que l'alphabet de tes marques n'écarte pas. */
export const viable = (a: Analysis): CountryScore[] => (a.scores ?? []).filter((s) => !excluded(a, s.code));

export function clearLeader(a: Analysis): CountryScore | null {
  const [first, second] = viable(a);
  if (!first) return null;
  const ok = first.probability >= engine.leader.min && first.probability - (second?.probability ?? 0) >= engine.leader.margin;
  return ok ? first : null;
}

/** Pays entre lesquels StreetCLIP hésite : les premiers, au moins 10 % chacun (quatre au plus). */
export const contenders = (a: Analysis): CountryScore[] =>
  viable(a).filter((s, i) => i === 0 || s.probability >= 0.1).slice(0, 4);

/** Le modèle de vision a vu du texte sans pouvoir le lire (trop petit ou flou). */
export function unreadableText(a: Analysis): boolean {
  if (a.vision.status !== "done") return false;
  const text = a.vision.fiche.panneaux_et_texte;
  const all = Array.isArray(text) ? text.join(" ") : String(text ?? "");
  return /illisible/i.test(all);
}

/** Pays en tête : prouvé (certain, les autres écartés) ou lu par l'IA (très probable, les autres restent). */
export function headCountry(a: Analysis): { code: string; certain: boolean; source: Conclusion["source"] | "lock" } | null {
  const locked = lockedCountry(a);
  if (locked) return { code: locked, certain: true, source: "lock" }; // verrou : astuces et zones s'y centrent
  const certain = certainProof(a);
  if (certain) return { code: certain.country, certain: true, source: certain.source };
  const proof = proofOf(a);
  return proof ? { code: proof.country, certain: false, source: proof.source } : null;
}

/** Astuces Plonk It à afficher : le pays en tête d'abord (seul lui s'il est certain), puis les probables. */
export function tipsByCountry(a: Analysis): { code: string; tips: SimilarTip[] }[] {
  const head = headCountry(a);
  // Pays verrouillé hors des candidats de StreetCLIP : ses astuces arrivent à part (message « similar »).
  if (head?.source === "lock") return [{ code: head.code, tips: a.similar?.[head.code] ?? [] }].filter((c) => c.tips.length);
  return viable(a)
    .filter((s) => !head?.certain || s.code === head.code)
    .sort((x, y) => Number(y.code === head?.code) - Number(x.code === head?.code))
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

/** Zones à dessiner : celles du pays en tête (prouvé ou lu par l'IA), sinon toutes. Un pays lu mais sans
 * zone à lui garde les zones de tous les pays : il n'est pas certain. */
export function visibleZones(a: Analysis): Zone[] {
  if (a.cloud.status !== "done") return [];
  const head = headCountry(a);
  if (!head) {
    // L'alphabet de tes marques écarte des pays : seulement les zones des pays qui restent possibles.
    const allowed = a.verdict?.allowed;
    const kept = allowed ? allowed.flatMap((c) => a.cloud.status === "done" ? a.cloud.data.zones_by_country[c] ?? [] : []) : [];
    return kept.length ? kept : a.cloud.data.zones;
  }
  return a.cloud.data.zones_by_country[head.code] ?? (head.certain ? [] : a.cloud.data.zones);
}

/** Une marque : un indice entouré sur la vue figée, découpé dans l'image brute et transcrit par l'IA. */
export interface Mark {
  /** Numéro affiché (①, ②…), continu sur toute l'analyse. */
  n: number;
  status: "pending" | "done" | "error";
  /** Découpe telle qu'envoyée au modèle (agrandie si elle était petite). */
  thumbnail: string;
  /** Facteur d'agrandissement appliqué (1 = taille d'origine). */
  scale: number;
  /** Ce que les règles locales tirent de son texte (alphabet, lettres, mots, lieux). */
  evidence?: Evidence[];
  /** Lignes lues mot pour mot (vide : pas de texte). */
  text: string[];
  unreadable: boolean;
  /** Ce que montre la marque (plaque de rue, enseigne…), selon l'IA. */
  object: string;
  script: string;
  seconds?: number;
  error?: string;
  /** Début de la lecture (horloge locale) : le bandeau d'activité compte depuis là, pas depuis la capture. */
  startedAt?: number;
}

/** Numéro de marque en chiffre cerclé (① à ⑳). */
export const circled = (n: number) => (n >= 1 && n <= 20 ? String.fromCodePoint(0x245f + n) : `(${n})`);

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
  /** Traduction des astuces en cours (null : rien à traduire), terminée, ou ce qui est resté en anglais. */
  translation: "pending" | "done" | string | null;
  /** Lots de traduction pas encore revenus : à 0, la traduction est finie, réussie ou non. */
  translationLeft: number;
  translationError: string | null;
  clipMs: number | null;
  labelled: { country: string; guessed: string; found: boolean | null } | null;
  /** Nuage de la carte : off (PLONK désactivé ou absent), en cours, prêt, ou en échec. */
  cloud: { status: "off" } | { status: "pending" } | { status: "done"; data: Cloud } | { status: "error"; error: string };
  vision:
    | { status: "off" }
    | { status: "pending"; model: string }
    | { status: "done"; model: string; seconds: number; fiche: Fiche }
    | { status: "error"; error: string };
  /** Indices entourés par le joueur, dans l'ordre de leur numéro. */
  marks: Mark[];
  /** Ce que les marques lues prouvent ensemble (null : aucune marque lue). */
  verdict: Verdict | null;
  /** Verrous de la capture (null : aucun pour l'instant). */
  locks: Locks | null;
}

export const engine = reactive({
  connected: false,
  capture: { alive: false, starting: true, message: "connexion au moteur…" },
  streetclip: { ready: false, message: "" },
  /** key : d'où vient la clé API et ses 4 derniers caractères (jamais la clé), null si absente. */
  vision: { enabled: false, ready: false, model: "", key: null as { source: string; end: string } | null },
  metas: { count: 0, message: "", judge: true },
  dataset: { enabled: false, ask_guessed: true },
  plonkit: { enabled: false, status: "off", message: "", tips: 0 },
  plonk: { enabled: false, ready: false, message: "" },
  /** uses / not_yet : ce que le coach tire d'une marque, rappelé sur l'écran des marques. */
  marks: { enabled: false, max: 9, uses: [] as string[], not_yet: [] as string[] },
  places: { enabled: false, ready: false, message: "" },
  locks: { enabled: false },
  map: { enabled: false, tile_url: "", attribution: "", attribution_url: "", tile_filter: "", tile_filter_close: "",
         close_zoom: 11, max_zoom: 13 },
  countries: [] as string[],
  /** Niveau d'aide : 1 où regarder, 2 + ce que voit l'IA, 3 + pays et indices, 4 + synthèse de la réponse. */
  helpLevel: 4,
  /** Une preuve lue avec certitude forte met son pays en tête et écarte les autres. */
  trustProof: true,
  /** Sans preuve, un pays n'est donné en réponse que s'il se détache (probabilité et avance sur le 2ᵉ). */
  leader: { min: 0.4, margin: 0.15 },
  /** « Tout effacer » fait : le moteur attend d'être relancé. */
  erased: false,
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
      marks: typeof engine.marks;
      places: typeof engine.places;
      locks: typeof engine.locks;
      map: typeof engine.map;
      countries: string[];
      erased: boolean;
      help_level: number;
      trust_proof: boolean;
      leader: { min: number; margin: number };
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
      batches: number;
      cloud: boolean;
    }
  | ({ type: "cloud"; id: string } & (Cloud | { error: string }))
  | { type: "tips_translated"; id: string; translations: Record<string, string>; error?: string }
  | { type: "vision_pending"; id: string; model: string }
  | { type: "vision"; id: string; model: string; seconds: number; fiche: Fiche }
  | { type: "vision_error"; id: string; error: string }
  | { type: "labelled"; id: string; country: string; guessed: string; found: boolean | null; progress: Progress }
  | { type: "lookfor"; id: string; lookfor: LookFor[] }
  | ({ type: "mark"; id: string } & Partial<Mark> & Pick<Mark, "n" | "status">)
  | { type: "freeze"; id: string }
  | ({ type: "verdict"; id: string } & Verdict)
  | { type: "mark_removed"; id: string; n: number }
  | ({ type: "locks"; id: string } & Locks)
  | { type: "similar"; id: string; similar: Record<string, SimilarTip[]>; batches: number }
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
      engine.marks = msg.marks;
      engine.places = msg.places;
      engine.locks = msg.locks;
      engine.map = msg.map;
      engine.countries = msg.countries;
      engine.erased = msg.erased ?? false;
      engine.helpLevel = msg.help_level;
      engine.trustProof = msg.trust_proof;
      engine.leader = msg.leader;
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
        translationLeft: 0,
        translationError: null,
        clipMs: null,
        labelled: null,
        cloud: { status: "off" },
        vision: engine.vision.enabled ? { status: "pending", model: engine.vision.model } : { status: "off" },
        marks: [],
        verdict: null,
        locks: null,
      };
      break;
    case "streetclip":
      if (cur?.id === msg.id) {
        cur.scores = msg.scores;
        cur.lookfor = msg.lookfor;
        cur.similar = { ...(cur.similar ?? {}), ...msg.similar }; // le pays verrouillé a pu arriver avant
        if (msg.translating) cur.translation = "pending";
        cur.translationLeft += msg.batches;
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
        // Un message par lot, réussi ou non : « en cours » jusqu'au dernier, jamais au-delà.
        cur.translationLeft = Math.max(0, cur.translationLeft - 1);
        if (msg.error) cur.translationError = msg.error;
        if (cur.translationLeft === 0 || all.every((tip) => tip.translated)) {
          cur.translation = all.every((tip) => tip.translated) ? "done"
            : `certaines astuces sont restées en anglais (${cur.translationError ?? "pas de réponse"})`;
        }
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
    case "mark": {
      if (cur?.id !== msg.id) break;
      const { type: _type, id: _id, ...fields } = msg;
      const known = cur.marks.find((m) => m.n === msg.n);
      if (known) Object.assign(known, fields);
      else {
        cur.marks.push({ thumbnail: "", scale: 1, text: [], unreadable: false, object: "", script: "", startedAt: Date.now(), ...fields });
        cur.marks.sort((a, b) => a.n - b.n);
      }
      break;
    }
    case "verdict": {
      if (cur?.id !== msg.id) break;
      const { type: _type, id: _id, ...verdict } = msg;
      cur.verdict = verdict;
      break;
    }
    case "mark_removed":
      if (cur?.id === msg.id) cur.marks = cur.marks.filter((m) => m.n !== msg.n);
      break;
    case "locks":
      if (cur?.id === msg.id) {
        cur.locks = { held: msg.held, rejected: msg.rejected, proposal: msg.proposal, read_regions: msg.read_regions ?? [],
                      region_bounds: msg.region_bounds ?? null };
      }
      break;
    case "similar": // astuces du pays verrouillé, ajoutées à celles des candidats
      if (cur?.id === msg.id) {
        cur.similar = { ...(cur.similar ?? {}), ...msg.similar };
        if (msg.batches) {
          cur.translationLeft += msg.batches;
          cur.translation = "pending";
        }
      }
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
/** « Marquer » : fige la vue ; la fenêtre des marques s'ouvre en plein écran. */
export const requestFreeze = () => request("/marks/freeze");
/** Retire une marque dont la lecture est fausse : la conclusion est recalculée sans elle. */
export const removeMark = (id: string, n: number) => request("/marks/remove", { id, n });
export const restartSharing = () => request("/capture/restart");
export const reselectWindow = () => request("/capture/reselect");
/** « C'était où ? » : pays réel, et pays répondu (vide si tu ne sais plus) ou simple « trouvé ? ». */
export const labelCapture = (id: string, country: string, guessed: string, found: boolean | null = null, link = "") =>
  request("/label", { id, country, guessed, found, link });
/** Vrai lieu lu dans un lien Google Maps (jamais ouvert) : position, pays, région ; ou la raison du refus. */
export async function previewTruth(link: string): Promise<
  { lat: number; lon: number; country: string; region: string; region_name: string } | { error: string }> {
  try {
    const res = await fetch(ENGINE_URL + "/label/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ link }),
    });
    const body = await res.json().catch(() => ({}));
    return res.ok ? body : { error: typeof body.detail === "string" ? body.detail : `refusé (${res.status})` };
  } catch {
    return { error: "le moteur ne répond pas" };
  }
}
export const refreshPlonkit = () => request("/plonkit/refresh");
/** « Tout effacer » (RGPD) : ce qui partirait, avec les tailles. */
export interface EraseGroup { id: string; label: string; files: number; size: number; precious: boolean; optional: boolean }
export const erasePlan = () => getJSON<{ groups: EraseGroup[] }>("/storage/erase");
/** Efface tout ce qui te concerne, puis relance le moteur (Tauri) et l'interface, qui repartent de zéro. */
export async function eraseEverything(models: boolean): Promise<string | null> {
  const res = await request("/storage/erase", { confirm: "EFFACER", models });
  if (!res?.ok) return engine.error ?? "Effacement impossible.";
  try {
    localStorage.clear(); // l'état de l'interface (sections ouvertes…) part aussi
  } catch {
    /* stockage indisponible : rien à effacer */
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("restart_engine");
  } catch {
    return "Données effacées. Relance l'application pour repartir de zéro.";
  }
  window.location.reload();
  return null;
}
/** Clé API NVIDIA : écrite par le moteur dans un fichier lisible par toi seul ; vide = l'oublier. */
export async function saveApiKey(key: string): Promise<string | null> {
  const res = await request("/settings/api-key", { key });
  return res?.ok ? null : engine.error ?? "Enregistrement impossible.";
}
/** Verrouille un pays, une région ou une ville pour la capture (ou accepte la ville proposée). */
export const setLock = (id: string, lock: Pick<Lock, "level" | "country"> & Partial<Lock>) =>
  request("/locks", { id, level: lock.level, country: lock.country, region: lock.region ?? "", name: lock.name ?? "",
                      lat: lock.lat ?? null, lon: lock.lon ?? null });
/** ✕ sur un verrou ou sur la ville proposée : écarté pour toute la capture. */
export const rejectLock = (id: string, level: Lock["level"] | "proposal") => request("/locks/reject", { id, level });
/** Recherche d'une région ou d'une ville dans l'index local (sans réseau, sans bloquer les boutons). */
export async function searchPlaces(level: "region" | "city", q: string, country: string, region = ""): Promise<PlaceFound[]> {
  try {
    const res = await fetch(ENGINE_URL + "/locks/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level, q, country, region }),
    });
    return res.ok ? ((await res.json()).results as PlaceFound[]) : [];
  } catch {
    return [];
  }
}
/** Vide un élément du stockage (Réglages › Stockage) ; renvoie l'inventaire à jour et la place libérée. */
export async function clearStorage(id: string): Promise<{ freed: number; items: unknown[] } | null> {
  const res = await request("/storage/clear", { id });
  return res?.ok ? ((await res.json()) as { freed: number; items: unknown[] }) : null;
}

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
/** Forme de comparaison d'un nom : minuscules, sans accents (« Égypte » ~ « egy »). */
export const normalise = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
/** Nombre à la française : « 13,2 ». */
export const fr = (n: number) => n.toLocaleString("fr-FR", { maximumFractionDigits: 1 });
export const flag = (code: string) =>
  String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));

// --- Réglages ------------------------------------------------------------------------------------
export type Settings = Record<string, Record<string, unknown>>;
/** Réglages réservés au fichier (sécurité) : valeur et raison, affichés en lecture seule. */
export type FileOnly = Record<string, Record<string, { value: unknown; why: string }>>;

/** Enregistre un seul réglage, tout de suite ; renvoie l'erreur éventuelle et s'il attend un redémarrage. */
export async function saveSetting(section: string, key: string, value: unknown): Promise<{ error: string | null; restart: boolean }> {
  try {
    const res = await fetch(ENGINE_URL + "/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [section]: { [key]: value } }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) return { error: typeof body.detail === "string" ? body.detail : `Refusé (${res.status}).`, restart: false };
    return { error: null, restart: Array.isArray(body.restart) && body.restart.length > 0 };
  } catch {
    return { error: "Le moteur ne répond pas.", restart: false };
  }
}

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
