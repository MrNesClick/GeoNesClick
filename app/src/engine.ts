// Connexion au moteur Python : WebSocket pour les résultats poussés, HTTP pour les commandes.
import { reactive } from "vue";

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

export type Fiche = Record<string, string | string[]>;

export interface Analysis {
  id: string;
  at: string;
  thumbnail: string;
  captureMs: number;
  scores: CountryScore[] | null;
  lookfor: LookFor[] | null;
  clipMs: number | null;
  countriesShown: boolean;
  labelled: { country: string; guessed: string; found: boolean | null } | null;
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
  countries: [] as string[],
  level: 1,
  revealCountries: false,
  revealed: false,
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
      countries: string[];
      level: number;
      reveal_countries: boolean;
    }
  | { type: "capture"; id: string; at: string; thumbnail: string; ms: number }
  | { type: "streetclip"; id: string; ms: number; scores: CountryScore[]; lookfor: LookFor[] }
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
      engine.countries = msg.countries;
      engine.level = msg.level;
      engine.revealCountries = msg.reveal_countries;
      break;
    case "capture":
      engine.error = null;
      engine.revealed = engine.level >= 2;
      engine.current = {
        id: msg.id,
        at: msg.at,
        thumbnail: msg.thumbnail,
        captureMs: msg.ms,
        scores: null,
        lookfor: null,
        clipMs: null,
        countriesShown: engine.revealCountries,
        labelled: null,
        vision: engine.vision.enabled ? { status: "pending", model: engine.vision.model } : { status: "off" },
      };
      break;
    case "streetclip":
      if (cur?.id === msg.id) {
        cur.scores = msg.scores;
        cur.lookfor = msg.lookfor;
        cur.clipMs = msg.ms;
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
/** Verdict du joueur sur un indice de l'amorce ; le moteur l'écrit dans mes-metas.toml. */
export const judgeHint = (category: string, hint: string, verdict: "right" | "wrong") =>
  request("/metas/judge", { category, hint, verdict, id: engine.current?.id ?? "" });

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
