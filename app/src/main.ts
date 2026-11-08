import { createApp } from "vue";
import App from "./App.vue";
import MarksOverlay from "./MarksOverlay.vue";
import "./style.css";
import { connect } from "./engine";

// Two windows, a single page: the coach, and the full-screen marks window (tauri.conf.json).
if (new URLSearchParams(location.search).get("view") === "marks") {
  createApp(MarksOverlay).mount("#app");
} else {
  connect();
  createApp(App).mount("#app");
}
