// Connexion au moteur Python : WebSocket pour les résultats poussés, HTTP pour les commandes.
import { reactive } from "vue";

const ENGINE_URL: string = import.meta.env.VITE_ENGINE_URL ?? "http://127.0.0.1:47615";
const WS_URL = ENGINE_URL.replace(/^http/, "ws") + "/ws";

export interface CountryScore {
  name: string;
  code: string;
  probability: number;
}

export type Fiche = Record<string, string | string[]>;

export interface Analysis {
  id: string;
  at: string;
  thumbnail: string;
  captureMs: number;
  scores: CountryScore[] | null;
  clipMs: number | null;
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
  level: 1,
  revealed: false,
  busy: false,
  error: null as string | null,
  current: null as Analysis | null,
});

type Message =
  | { type: "state"; capture: typeof engine.capture; streetclip: typeof engine.streetclip; vision: typeof engine.vision; level: number }
  | { type: "capture"; id: string; at: string; thumbnail: string; ms: number }
  | { type: "streetclip"; id: string; ms: number; scores: CountryScore[] }
  | { type: "vision_pending"; id: string; model: string }
  | { type: "vision"; id: string; model: string; seconds: number; fiche: Fiche }
  | { type: "vision_error"; id: string; error: string }
  | { type: "error"; message: string };

function handle(msg: Message) {
  const cur = engine.current;
  switch (msg.type) {
    case "state":
      engine.capture = msg.capture;
      engine.streetclip = msg.streetclip;
      engine.vision = msg.vision;
      engine.level = msg.level;
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
        clipMs: null,
        vision: engine.vision.enabled ? { status: "pending", model: engine.vision.model } : { status: "off" },
      };
      break;
    case "streetclip":
      if (cur?.id === msg.id) {
        cur.scores = msg.scores;
        cur.clipMs = msg.ms;
      }
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
    case "error":
      engine.error = msg.message;
      break;
  }
}

export function connect() {
  const ws = new WebSocket(WS_URL);
  ws.onopen = () => (engine.connected = true);
  ws.onmessage = (event) => handle(JSON.parse(event.data) as Message);
  ws.onclose = () => {
    engine.connected = false;
    setTimeout(connect, 1500); // le moteur démarre en quelques secondes
  };
}

async function post(path: string) {
  engine.busy = true;
  try {
    const res = await fetch(ENGINE_URL + path, { method: "POST" });
    if (!res.ok) engine.error = `Le moteur a répondu ${res.status}.`;
  } catch {
    engine.error = "Le moteur ne répond pas.";
  } finally {
    engine.busy = false;
  }
}

export const requestCapture = () => post("/capture");
export const restartSharing = () => post("/capture/restart");
export const reselectWindow = () => post("/capture/reselect");
