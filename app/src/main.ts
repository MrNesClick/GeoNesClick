import { createApp } from "vue";
import App from "./App.vue";
import MarksOverlay from "./MarksOverlay.vue";
import Setup from "./components/Setup.vue";
import "./style.css";
import { connect } from "./engine";

/** AppImage without an installed (or up-to-date) engine: the first-launch assistant comes first. */
async function setupNeeded(): Promise<boolean> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const status = (await invoke("setup_status")) as { bundled: boolean; needed: boolean };
    return status.bundled && status.needed;
  } catch {
    return false; // outside Tauri (plain browser): nothing to install
  }
}

async function resize(width: number, height: number) {
  try {
    const { getCurrentWindow, LogicalSize } = await import("@tauri-apps/api/window");
    const win = getCurrentWindow();
    await win.setSize(new LogicalSize(width, height));
    await win.center();
  } catch {
    /* outside Tauri, or not allowed: the window keeps its size */
  }
}

// Two windows, a single page: the coach, and the full-screen marks window (tauri.conf.json).
if (new URLSearchParams(location.search).get("view") === "marks") {
  createApp(MarksOverlay).mount("#app");
} else {
  connect(); // retries until the engine answers, so it also covers the start after the assistant
  setupNeeded().then((needed) => {
    if (!needed) {
      createApp(App).mount("#app");
      return;
    }
    const setup = createApp(Setup, {
      onDone: () => {
        setup.unmount();
        resize(460, 940); // the coach's size (tauri.conf.json)
        createApp(App).mount("#app");
      },
    });
    resize(860, Math.min(980, screen.availHeight - 40)); // an installer needs more room than the coach's column
    setup.mount("#app");
  });
}
