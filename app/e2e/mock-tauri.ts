// The Rust side, simulated with Tauri's own mocks for the interface tests (loaded by e2e/harness.html only).
// Each test sets window.__GNC_TAURI__ before the page loads: the answer of each command, { sequence: [...] } for
// successive answers (the last one repeats), or { error } for a refusal. Every call is recorded in __GNC_CALLS__.
import { emit } from "@tauri-apps/api/event";
import { mockIPC, mockWindows } from "@tauri-apps/api/mocks";

type Answer = unknown;
declare global {
  interface Window {
    __GNC_TAURI__?: Record<string, Answer>;
    __GNC_CALLS__: { cmd: string; args: unknown }[];
    __GNC_EMIT__: typeof emit;
  }
}

// Commands that need no answer from the test (their result is not used).
const SILENT = new Set(["set_language", "restart_engine", "setup_apply", "set_shortcuts", "set_menu_entry", "remove_integration"]);

window.__GNC_CALLS__ = [];
window.__GNC_EMIT__ = emit;
mockWindows("main");
mockIPC(
  (cmd, args) => {
    window.__GNC_CALLS__.push({ cmd, args });
    const answers = window.__GNC_TAURI__ ?? {};
    if (!(cmd in answers)) {
      if (SILENT.has(cmd) || cmd.startsWith("plugin:")) return null;
      throw `unexpected command in the test: ${cmd}`;
    }
    let answer = answers[cmd];
    if (answer && typeof answer === "object" && "sequence" in answer) {
      const list = (answer as { sequence: unknown[] }).sequence;
      answer = list.length > 1 ? list.shift() : list[0];
    }
    if (answer && typeof answer === "object" && "error" in answer) throw (answer as { error: string }).error;
    return answer;
  },
  { shouldMockEvents: true },
);
