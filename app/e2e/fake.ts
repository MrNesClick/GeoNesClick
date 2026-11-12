// The engine and the Rust side, simulated for the interface tests. The engine's answers are the fixtures written by
// the real engine (make_fixtures.py); a test changes only what its scenario needs.
import { readFileSync } from "node:fs";
import type { Page, WebSocketRoute } from "@playwright/test";

const ENGINE = "http://127.0.0.1:47615";

export function fixture<T = any>(name: string): T {
  return JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf-8")) as T;
}

/** Answers of the Rust commands (see mock-tauri.ts), set before the page loads. */
export async function tauri(page: Page, answers: Record<string, unknown>) {
  await page.addInitScript((a) => {
    window.__GNC_TAURI__ = a;
  }, answers);
}

/** The Rust commands the page called, in order. */
export async function tauriCalls(page: Page): Promise<string[]> {
  return page.evaluate(() => window.__GNC_CALLS__.map((c) => c.cmd));
}

/** The arguments of each call of a Rust command, in order. */
export async function tauriArgs(page: Page, cmd: string): Promise<unknown[]> {
  return page.evaluate((name) => window.__GNC_CALLS__.filter((c) => c.cmd === name).map((c) => c.args), cmd);
}

export interface FakeEngine {
  /** false: the engine does not answer yet (starting): connections refused. */
  up: boolean;
  get: Record<string, unknown>;
  post: Record<string, unknown>;
  /** The POST requests received, with their body. */
  posts: { path: string; body: unknown }[];
  /** Sends a message to every connected window, like the engine's broadcast. */
  send(message: unknown): void;
}

export async function fakeEngine(page: Page, options: { up?: boolean; state?: object } = {}): Promise<FakeEngine> {
  const sockets: WebSocketRoute[] = [];
  const engine: FakeEngine = {
    up: options.up ?? true,
    get: {
      "/settings": fixture("settings.json"),
      "/settings/file-only": fixture("settings-file-only.json"),
      "/storage": fixture("storage.json"),
      "/storage/erase": fixture("storage-erase.json"),
      "/progress": fixture("progress.json"),
      "/models": { models: [] },
    },
    post: {},
    posts: [],
    send: (message) => sockets.forEach((ws) => ws.send(JSON.stringify(message))),
  };
  const state = { ...fixture("state.json"), ...options.state };
  const cors = { "access-control-allow-origin": "*", "access-control-allow-headers": "*",
                 "access-control-allow-methods": "GET, POST, OPTIONS" };
  await page.route(`${ENGINE}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    if (!engine.up) return route.abort("connectionrefused");
    if (request.method() === "POST") {
      engine.posts.push({ path, body: request.postDataJSON() });
      return route.fulfill({ headers: cors, json: engine.post[path] ?? { ok: true } });
    }
    const body = engine.get[path];
    return route.fulfill(body === undefined
      ? { status: 404, headers: cors, json: { detail: `${path}: not in the fake engine` } }
      : { headers: cors, json: body });
  });
  await page.routeWebSocket(`${ENGINE.replace("http", "ws")}/ws`, (ws) => {
    if (!engine.up) {
      ws.close();
      return;
    }
    sockets.push(ws);
    ws.send(JSON.stringify({ type: "state", ...state }));
  });
  return engine;
}
