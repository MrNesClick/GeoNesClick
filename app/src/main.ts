import { createApp } from "vue";
import App from "./App.vue";
import MarksOverlay from "./MarksOverlay.vue";
import "./style.css";
import { connect } from "./engine";

// Deux fenêtres, une seule page : le coach, et la fenêtre plein écran des marques (tauri.conf.json).
if (new URLSearchParams(location.search).get("view") === "marks") {
  createApp(MarksOverlay).mount("#app");
} else {
  connect();
  createApp(App).mount("#app");
}
