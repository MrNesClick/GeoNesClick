// Connection to the Python engine: WebSocket for pushed results, HTTP for commands.
import { reactive } from "vue";
import { openUrl } from "@tauri-apps/plugin-opener";
import { setLanguage, t, unreadableWords } from "./i18n";

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
  /** "mine" (my-metas.toml) or "seed" (metas_amorce.toml). */
  source: "mine" | "seed";
  verified: boolean;
  /** Seed clue to settle with "Right" / "Wrong" (empty: not a seed clue). */
  seed: string;
}

/** A category to look at to tell the candidate countries apart. */
export interface LookFor {
  category: string;
  label: string;
  score: number;
  /** What to observe to decide, without naming a country. */
  looks: string[];
  hints: Hint[];
}

/** A Plonk It tip whose text resembles the view (CLIP comparison, local). */
export interface SimilarTip {
  /** Hash of the text: key of the translation. */
  id: string;
  text: string;
  /** Translation into the coach's language, if already known. */
  translated: string | null;
  section: string;
  category: string;
  url: string;
  score: number;
}

/** A real country often taken for another, with the metas that tell them apart. */
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

/** Conclusion: the local rules' one on your marks, otherwise the vision model's (whole view). */
export interface Conclusion {
  /** marks: local rules on the text of your marks; vision: reading of the whole view by the AI. */
  source: "marks" | "vision";
  country: string;
  region: string;
  proof: string;
  certainty: string;
  /** Confirmed by a local rule (word, domain, dialling code…). Measured: the model alone is sometimes wrong
   * with "strong certainty" (Slovakia on a misread "utca"); without confirmation, never "certain". */
  confirmed: boolean;
}

/** Reads the "conclusion" key of the sheet; null if missing, empty or a country unknown to the configuration. */
export function conclusionOf(fiche: Fiche): Conclusion | null {
  const c = fiche.conclusion;
  if (!c || typeof c !== "object") return null;
  const field = (key: string) => {
    const v = (c as Record<string, unknown>)[key];
    return typeof v === "string" ? v.trim() : "";
  };
  const country = field("country").toUpperCase();
  if (!engine.countries.includes(country)) return null;
  return {
    source: "vision", country, region: field("region"), proof: field("proof"),
    certainty: field("certainty").toLowerCase(),
    confirmed: false, // the AI alone is never "certain": only the local rules confirm
  };
}

/** A proof drawn from a mark by a local rule. */
export interface Evidence {
  kind: "alphabet" | "letters" | "word" | "place" | "street";
  value: string;
  label: string;
  countries: string[];
  source: string;
  /** Why it does not count ("outside your candidate countries"); empty otherwise. */
  note?: string;
  /** Place: namesakes kept [latitude, longitude, country, GeoNames name, region]. */
  points?: [number, number, string, string, string?][];
}

/** A lock: what is set for the capture (country › region › city), by the coach or by you. */
export interface Lock {
  level: "country" | "region" | "city";
  country: string;
  /** GeoNames code of the region ("FR.75"): region, and city if known. */
  region: string;
  /** Name of the region or city (the country: countryName). */
  name: string;
  lat: number | null;
  lon: number | null;
  by: "coach" | "user";
  /** What made the coach set it ("marks 1, 2"). */
  why: string;
}

export interface Locks {
  held: Partial<Record<Lock["level"], Lock>>;
  /** Rejected for the whole capture: the coach does not lock them again. */
  rejected: Lock[];
  /** City suggested by the coach: never locked without you. */
  proposal: Lock | null;
  /** Regions of the places read in your marks, offered in one click (several: your call). */
  read_regions: { code: string; name: string; marks: number[]; places: string[] }[];
  /** Extent of the chosen region [south, west, north, east], from its GeoNames places (no outline). */
  region_bounds: [number, number, number, number] | null;
}

/** Result of the "+" search (local GeoNames index). */
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

/** Locked country (by you or by the coach), or null. */
export const lockedCountry = (a: Analysis): string | null => a.locks?.held.country?.country ?? null;

/** What the marks prove together (the engine's local rules, evidence.py). */
export interface Verdict {
  country: string;
  /** certain (place + other proof, no contrary mark), probable (very likely), or "" */
  level: "certain" | "probable" | "";
  /** Countries the alphabet leaves possible; null: none ruled out. */
  allowed: string[] | null;
  scripts: string[];
  cites: { n: number; items: string[] }[];
  against: { n: number; country: string; items: string[] }[];
  conflict: string;
  /** Position estimated from the places read (and a sign's distances), null without a place. */
  location: Location | null;
  /** Distant namesakes ruled out ("LAAS" → Lasa, Italy, far from the other places read): they do not count. */
  ignored: { n: number; value: string; label: string; countries: string[] }[];
  /** Lone places, unconfirmed (2nd place, letter or word, StreetCLIP): mere clues. */
  unconfirmed: { n: number; value: string; country: string }[];
  /** Places read that your choices rule out (outside your country or region): greyed out on the map. */
  outside?: { n: number; name: string; label: string; lat: number; lon: number }[];
}

/** A place read on a mark, plotted on the map (GeoNames). */
export interface PlaceRead {
  n: number;
  name: string;
  label: string;
  km: number | null;
  lat: number;
  lon: number;
}

/** point: triangulated (several distances); ring: at a distance from a place; places: around the places. */
export type Location =
  | { kind: "point"; lat: number; lon: number; radius_km: number; places: PlaceRead[] }
  | { kind: "ring"; lat: number; lon: number; radius_km: number; spread_km: number; places: PlaceRead[] }
  | { kind: "places"; places: PlaceRead[] }
  /** Inconsistent distances (misread digit): at most radius_km from the closest place, always true. */
  | { kind: "rough"; lat: number; lon: number; radius_km: number; doubtful: { n: number; name: string; km: number }[];
      places: PlaceRead[] };

/** Country ruled out by the alphabet of your marks ("Cyrillic" excludes France). */
export const excluded = (a: Analysis, code: string): boolean =>
  !!a.verdict?.allowed && !a.verdict.allowed.includes(code);

/** Conclusion of the local rules on your marks, citing the marks that prove it. */
export function marksConclusion(a: Analysis): Conclusion | null {
  const v = a.verdict;
  if (!v?.country || !v.level) return null;
  return {
    source: "marks", country: v.country, region: "",
    proof: v.cites.map((c) => `${circled(c.n)} ${c.items.join(", ")}`).join(" · "),
    certainty: v.level === "certain" ? "strong" : "medium", confirmed: v.level === "certain",
  };
}

/** AI conclusion on the whole view that the alphabet of your marks contradicts (France on Cyrillic). */
export function rejectedVision(a: Analysis): Conclusion | null {
  const c = a.vision.status === "done" ? conclusionOf(a.vision.fiche) : null;
  return c && excluded(a, c.country) ? c : null;
}

/** The proof that counts: your marks first; otherwise the AI's reading, if the alphabet does not exclude it. */
export function proofOf(a: Analysis): Conclusion | null {
  const marks = marksConclusion(a);
  if (marks) return marks;
  const vision = a.vision.status === "done" ? conclusionOf(a.vision.fiche) : null;
  return vision && !excluded(a, vision.country) ? vision : null;
}

/** Label of a proof according to its source and its confirmation. */
export function proofLabel(c: Conclusion): string {
  if (c.source === "marks") return t(c.confirmed ? "proof.marks_certain" : "proof.marks_likely");
  return t(c.certainty === "strong" ? "proof.ai_strong" : "proof.ai_medium");
}

/** CERTAIN proof: strong, confirmed by a local rule, and the "a proof read settles it" setting on. */
export function certainProof(a: Analysis): Conclusion | null {
  const proof = proofOf(a);
  return engine.trustProof && proof?.certainty === "strong" && proof.confirmed ? proof : null;
}

/** StreetCLIP countries that the alphabet of your marks does not rule out. */
export const viable = (a: Analysis): CountryScore[] => (a.scores ?? []).filter((s) => !excluded(a, s.code));

/** Country that clearly stands out according to StreetCLIP, or null: the coach then talks of hesitation. */
export function clearLeader(a: Analysis): CountryScore | null {
  const [first, second] = viable(a);
  if (!first) return null;
  const ok = first.probability >= engine.leader.min && first.probability - (second?.probability ?? 0) >= engine.leader.margin;
  return ok ? first : null;
}

/** Countries StreetCLIP hesitates between: the first ones, at least 10 % each (four at most). */
export const contenders = (a: Analysis): CountryScore[] =>
  viable(a).filter((s, i) => i === 0 || s.probability >= 0.1).slice(0, 4);

/** The vision model saw text without being able to read it (too small or blurry). */
export function unreadableText(a: Analysis): boolean {
  if (a.vision.status !== "done") return false;
  const text = a.vision.fiche.signs_and_text;
  const all = (Array.isArray(text) ? text.join(" ") : String(text ?? "")).toLowerCase();
  // The model writes it in the UI's language: the word of every catalog ("unreadable", "illisible"…).
  return unreadableWords().some((w) => all.includes(w));
}

/** Leading country: proven (certain, the others ruled out) or read by the AI (very likely, the others stay). */
export function headCountry(a: Analysis): { code: string; certain: boolean; source: Conclusion["source"] | "lock" } | null {
  const locked = lockedCountry(a);
  if (locked) return { code: locked, certain: true, source: "lock" }; // lock: tips and zones centre on it
  const certain = certainProof(a);
  if (certain) return { code: certain.country, certain: true, source: certain.source };
  const proof = proofOf(a);
  return proof ? { code: proof.country, certain: false, source: proof.source } : null;
}

/** Plonk It tips to show: the leading country first (only it if it is certain), then the likely ones. */
export function tipsByCountry(a: Analysis): { code: string; tips: SimilarTip[] }[] {
  const head = headCountry(a);
  // Locked country outside StreetCLIP's candidates: its tips arrive separately ("similar" message).
  if (head?.source === "lock") return [{ code: head.code, tips: a.similar?.[head.code] ?? [] }].filter((c) => c.tips.length);
  return viable(a)
    .filter((s) => !head?.certain || s.code === head.code)
    .sort((x, y) => Number(y.code === head?.code) - Number(x.code === head?.code))
    .map((s) => ({ code: s.code, tips: a.similar?.[s.code] ?? [] }))
    .filter((c) => c.tips.length);
}

/** Zone where the view probably is: rounded outline around the densest PLONK positions. */
export interface Zone {
  /** Outline [latitude, longitude] in degrees. */
  polygon: [number, number][];
  /** Share of the cloud's positions in this zone (0 to 1). */
  part: number;
  width_km: number;
  height_km: number;
  /** Main countries of the zone and their share in it (two at most). */
  countries: [string, number][];
}

/** PLONK cloud of the view, summarised in zones by the engine (a lead for the map, never a country vote). */
export interface Cloud {
  zones: Zone[];
  /** The same zones computed country by country (countries with at least 5 % of the positions), to follow a proof. */
  zones_by_country: Record<string, Zone[]>;
  ms: number;
}

/** Zones to draw: those of the leading country (proven or read by the AI), otherwise all. A country read but
 * without a zone of its own keeps the zones of all countries: it is not certain. */
export function visibleZones(a: Analysis): Zone[] {
  if (a.cloud.status !== "done") return [];
  const head = headCountry(a);
  if (!head) {
    // The alphabet of your marks rules out countries: only the zones of the countries that remain possible.
    const allowed = a.verdict?.allowed;
    const kept = allowed ? allowed.flatMap((c) => a.cloud.status === "done" ? a.cloud.data.zones_by_country[c] ?? [] : []) : [];
    return kept.length ? kept : a.cloud.data.zones;
  }
  return a.cloud.data.zones_by_country[head.code] ?? (head.certain ? [] : a.cloud.data.zones);
}

/** A mark: a clue circled on the frozen view, cropped from the raw image and transcribed by the AI. */
export interface Mark {
  /** Displayed number (①, ②…), continuous over the whole analysis. */
  n: number;
  status: "pending" | "done" | "error";
  /** Crop as sent to the model (enlarged if it was small). */
  thumbnail: string;
  /** Enlargement factor applied (1 = original size). */
  scale: number;
  /** What the local rules draw from its text (alphabet, letters, words, places). */
  evidence?: Evidence[];
  /** Lines read word for word (empty: no text). */
  text: string[];
  unreadable: boolean;
  /** What the mark shows (street sign, shop sign…), according to the AI. */
  object: string;
  script: string;
  seconds?: number;
  error?: string;
  /** Start of the reading (local clock): the activity banner counts from there, not from the capture. */
  startedAt?: number;
}

/** Mark number as a circled digit (① to ⑳). */
export const circled = (n: number) => (n >= 1 && n <= 20 ? String.fromCodePoint(0x245f + n) : `(${n})`);

export interface Analysis {
  id: string;
  at: string;
  /** Time the capture was received (local clock), to show the elapsed time. */
  receivedAt: number;
  thumbnail: string;
  captureMs: number;
  /** The browser's bars were cut by a fixed share: their exact edge is learnt from the next capture. */
  guessedCrop: boolean;
  scores: CountryScore[] | null;
  lookfor: LookFor[] | null;
  similar: Record<string, SimilarTip[]> | null;
  /** Tip translation running (null: nothing to translate), finished, or what stayed in English. */
  translation: "pending" | "done" | string | null;
  /** Translation batches not back yet: at 0, the translation is over, successful or not. */
  translationLeft: number;
  translationError: string | null;
  clipMs: number | null;
  labelled: { country: string; guessed: string; found: boolean | null } | null;
  /** Map cloud: off (PLONK disabled or missing), running, ready, or failed. */
  cloud: { status: "off" } | { status: "pending" } | { status: "done"; data: Cloud } | { status: "error"; error: string };
  vision:
    | { status: "off" }
    | { status: "pending"; model: string }
    | { status: "done"; model: string; seconds: number; fiche: Fiche }
    | { status: "error"; error: string };
  /** Clues circled by the player, in the order of their number. */
  marks: Mark[];
  /** What the marks read prove together (null: no mark read). */
  verdict: Verdict | null;
  /** Locks of the capture (null: none so far). */
  locks: Locks | null;
}

export const engine = reactive({
  connected: false,
  capture: { alive: false, starting: true, message: t("engine.connecting") },
  streetclip: { ready: false, message: "" },
  /** key: where the API key comes from and its last 4 characters (never the key), null if missing. */
  vision: { enabled: false, ready: false, model: "", key: null as { source: string; end: string } | null },
  /** error: the metas could not be loaded (invalid my-metas file…); message says why. */
  metas: { count: 0, message: "", error: false, judge: true },
  dataset: { enabled: false, ask_guessed: true },
  plonkit: { enabled: false, status: "off", message: "", tips: 0 },
  plonk: { enabled: false, ready: false, message: "" },
  /** uses / not_yet: what the coach draws from a mark, recalled on the marks screen. */
  marks: { enabled: false, max: 9, uses: [] as string[], not_yet: [] as string[] },
  places: { enabled: false, ready: false, message: "" },
  locks: { enabled: false },
  map: { enabled: false, tile_url: "", attribution: "", attribution_url: "", tile_filter: "", tile_filter_close: "",
         close_zoom: 11, max_zoom: 13 },
  countries: [] as string[],
  /** Help level: 1 where to look, 2 + what the AI sees, 3 + countries and clues, 4 + synthesis of the answer. */
  helpLevel: 4,
  /** A proof read with strong certainty puts its country first and rules out the others. */
  trustProof: true,
  /** Without proof, a country is given as the answer only if it stands out (probability and lead over the 2nd). */
  leader: { min: 0.7, margin: 0.15 }, // the engine's defaults, until its first state message
  /** "Erase everything" done: the engine is waiting to be restarted. */
  erased: false,
  /** The engine was removed by "Erase everything": only closing is left. */
  uninstalled: false,
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
      /** UI language: coach.language when it has a catalog, en otherwise. */
      language: string;
      trust_proof: boolean;
      leader: { min: number; margin: number };
    }
  | { type: "capture"; id: string; at: string; thumbnail: string; ms: number; guessed_crop: boolean }
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
      setLanguage(msg.language); // a change in the Settings applies right away
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
        guessedCrop: msg.guessed_crop,
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
        cur.similar = { ...(cur.similar ?? {}), ...msg.similar }; // the locked country may have arrived before
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
        // One message per batch, successful or not: "running" until the last one, never beyond.
        cur.translationLeft = Math.max(0, cur.translationLeft - 1);
        if (msg.error) cur.translationError = msg.error;
        if (cur.translationLeft === 0 || all.every((tip) => tip.translated)) {
          cur.translation = all.every((tip) => tip.translated) ? "done"
            : t("engine.tips_left_in_english", { reason: cur.translationError ?? t("engine.no_answer") });
        }
      }
      break;
    case "lookfor": // recomputed after a "Right" / "Wrong" verdict
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
    case "similar": // tips of the locked country, added to those of the candidates
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
    setTimeout(connect, 1500); // the engine starts in a few seconds
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
      engine.error = typeof detail === "string" ? t("engine.refused", { detail }) : t("engine.status", { status: res.status });
    }
    return res;
  } catch {
    engine.error = t("engine.no_reply");
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
    /* no matter: the progress will come with the next label */
  }
}

export const requestCapture = () => request("/capture");
/** "Mark": freezes the view; the marks window opens in full screen. */
export const requestFreeze = () => request("/marks/freeze");
/** Removes a mark whose reading is wrong: the conclusion is recomputed without it. */
export const removeMark = (id: string, n: number) => request("/marks/remove", { id, n });
/** "Restart sharing" and "Change window": the GNOME picker opens (the remembered window is forgotten). */
export const reselectWindow = () => request("/capture/reselect");
/** "Where was it?": real country, and answered country (empty if you no longer know) or a simple "found?". */
export const labelCapture = (id: string, country: string, guessed: string, found: boolean | null = null, link = "") =>
  request("/label", { id, country, guessed, found, link });
/** True place read from a Google Maps link (never opened): position, country, region; or the reason for refusal. */
export async function previewTruth(link: string): Promise<
  { lat: number; lon: number; country: string; region: string; region_name: string } | { error: string }> {
  try {
    const res = await fetch(ENGINE_URL + "/label/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ link }),
    });
    const body = await res.json().catch(() => ({}));
    return res.ok ? body : { error: typeof body.detail === "string" ? body.detail : t("engine.refused_status", { status: res.status }) };
  } catch {
    return { error: t("engine.no_reply") };
  }
}
export const refreshPlonkit = () => request("/plonkit/refresh");
/** "Erase everything" (GDPR): what would go, with the sizes. */
export interface EraseGroup { id: string; label: string; files: number; size: number; precious: boolean; optional: boolean }
export const erasePlan = () => getJSON<{ groups: EraseGroup[] }>("/storage/erase");
/** Erases everything about you, then restarts the engine (Tauri) and the UI, which start again from scratch. */
export async function eraseEverything(models: boolean, removeEngine: boolean): Promise<string | null> {
  const res = await request("/storage/erase", { confirm: "ERASE", models });
  if (!res?.ok) return engine.error ?? t("engine.erase_failed");
  try {
    localStorage.clear(); // the UI state (open sections…) goes too
  } catch {
    /* storage unavailable: nothing to erase */
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    // The GNOME shortcuts and the menu entry go too, whatever was chosen; a failure is told, the rest goes on.
    const left = await invoke("remove_integration").then(() => null, (e) => t("engine.integration_left", { error: String(e) }));
    if (removeEngine) {
      // Uninstall: Tauri stops the engine then removes its installation; the app then only offers to close.
      await invoke("erase_engine");
      engine.uninstalled = true;
      return left;
    }
    await invoke("restart_engine");
    if (left) return left; // shown before the restart of the UI, which would hide it
  } catch (e) {
    return removeEngine ? String(e) : t("engine.erased_restart");
  }
  window.location.reload();
  return null;
}
/** NVIDIA API key: written by the engine to a file readable by you only; empty = forget it. */
export async function saveApiKey(key: string): Promise<string | null> {
  const res = await request("/settings/api-key", { key });
  return res?.ok ? null : engine.error ?? t("engine.save_failed");
}
/** Locks a country, a region or a city for the capture (or accepts the suggested city). */
export const setLock = (id: string, lock: Pick<Lock, "level" | "country"> & Partial<Lock>) =>
  request("/locks", { id, level: lock.level, country: lock.country, region: lock.region ?? "", name: lock.name ?? "",
                      lat: lock.lat ?? null, lon: lock.lon ?? null });
/** ✕ on a lock or on the suggested city: ruled out for the whole capture. */
export const rejectLock = (id: string, level: Lock["level"] | "proposal") => request("/locks/reject", { id, level });
/** Search for a region or a city in the local index (offline, without blocking the buttons). */
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
/** Empties a storage item (Settings › Storage); returns the updated inventory and the space freed. */
export async function clearStorage(id: string): Promise<{ freed: number; items: unknown[] } | null> {
  const res = await request("/storage/clear", { id });
  return res?.ok ? ((await res.json()) as { freed: number; items: unknown[] }) : null;
}

/** Changes the help level right away, then saves it in config.toml. */
export async function setHelpLevel(level: number) {
  engine.helpLevel = level;
  await saveSettings({ coach: { help_level: level } });
}

/** The metas categories (same ids as metas.py), in display order. */
export const CATEGORIES = ["language", "driving", "road_lines", "poles", "bollards", "plates", "signs", "domains",
                           "car", "vegetation", "architecture", "other"] as const;
/** A category's label in the UI's language; an unknown category is shown as is. */
const isCategory = (c: string): c is (typeof CATEGORIES)[number] => (CATEGORIES as readonly string[]).includes(c);
export const categoryLabel = (c: string) => (isCategory(c) ? t(`category.${c}`) : c);
/** Opens a Plonk It page in the browser (only these addresses are allowed by Tauri). */
export async function openPlonkit(url: string) {
  if (!url.startsWith("https://www.plonkit.net/")) return;
  try {
    await openUrl(url);
  } catch {
    engine.error = t("engine.no_browser");
  }
}

/** Markdown text of a tip as segments (bold or not), never interpreting HTML. */
export function markdownSegments(md: string): { text: string; bold: boolean }[] {
  const plain = md.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[_`#>]/g, "");
  return plain.split("**").map((text, i) => ({ text, bold: i % 2 === 1 })).filter((s) => s.text);
}

/** Player's verdict on a seed clue; the engine writes it to my-metas.toml. */
export const judgeHint = (seed: string, verdict: "right" | "wrong") =>
  request("/metas/judge", { seed, verdict, id: engine.current?.id ?? "" });

/** Country outlines (Natural Earth, served by the engine), loaded only once. */
let outlines: Promise<GeoJSON.FeatureCollection | null> | null = null;
export function countryOutlines(): Promise<GeoJSON.FeatureCollection | null> {
  outlines ??= getJSON<GeoJSON.FeatureCollection>("/map/countries").then((g) => {
    if (!g) outlines = null; // engine not ready yet: we will retry on the next map
    return g;
  });
  return outlines;
}

/** Opens the attribution page of the map background (only the OpenStreetMap address is allowed by Tauri). */
export async function openAttribution() {
  const url = engine.map.attribution_url;
  if (!url.startsWith("https://")) return;
  try {
    await openUrl(url);
  } catch {
    engine.error = t("engine.no_browser");
  }
}

// --- Countries: names (in the UI's language) and flags ----------------------------------------------
export { countryName, num } from "./i18n";
/** Comparison form of a name: lower case, without accents ("Égypte" ~ "egy"). */
export const normalise = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
export const flag = (code: string) =>
  String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));

// --- Settings ------------------------------------------------------------------------------------
export type Settings = Record<string, Record<string, unknown>>;
/** File-only settings (security): value and reason, shown read-only. */
export type FileOnly = Record<string, Record<string, { value: unknown; why: string }>>;

/** Saves a single setting, right away; returns the error, if any, and whether it awaits a restart. */
export async function saveSetting(section: string, key: string, value: unknown): Promise<{ error: string | null; restart: boolean }> {
  try {
    const res = await fetch(ENGINE_URL + "/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [section]: { [key]: value } }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) return { error: typeof body.detail === "string" ? body.detail : t("engine.refused_status", { status: res.status }), restart: false };
    return { error: null, restart: Array.isArray(body.restart) && body.restart.length > 0 };
  } catch {
    return { error: t("engine.no_reply"), restart: false };
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
  return engine.error ?? t("engine.save_failed");
}

/** Model test: separate call, so as not to block the capture during these few seconds. */
export async function testModel(model: string): Promise<{ ok: boolean; seconds?: number; error?: string }> {
  try {
    const res = await fetch(ENGINE_URL + "/models/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    });
    if (res.ok) return await res.json();
    return { ok: false, error: res.status === 422 ? t("engine.invalid_model") : t("engine.status", { status: res.status }) };
  } catch {
    return { ok: false, error: t("engine.no_reply") };
  }
}
