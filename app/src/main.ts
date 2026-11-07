import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";
import { connect } from "./engine";

connect();
createApp(App).mount("#app");
