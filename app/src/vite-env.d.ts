/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}

interface ImportMetaEnv {
  /** URL du moteur Python (défaut : http://127.0.0.1:47615) */
  readonly VITE_ENGINE_URL?: string;
}
