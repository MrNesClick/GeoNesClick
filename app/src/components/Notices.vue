<script setup lang="ts">
// Notes the coach shows once, then never again: closed by the player, they are forgotten.
// - after an installation or an update (Setup.vue, placeApp): where GeoNesClick is installed, the downloaded AppImage
//   that may now be deleted, and for an update what changed since the previous version.
import { ref } from "vue";
import { t } from "../i18n";
import WhatsNew, { type Release } from "./WhatsNew.vue";

interface Installed { version: string; dir: string; file: string | null; whats_new?: Release[] }
const NOTICE = "geonesclick.notice";

function read(): Installed | null {
  try {
    const saved = JSON.parse(localStorage.getItem(NOTICE) ?? "null");
    return saved && typeof saved.dir === "string" && (typeof saved.file === "string" || saved.whats_new?.length) ? saved : null;
  } catch {
    return null; // storage unavailable or damaged: no note
  }
}

const installed = ref(read());
function close() {
  installed.value = null;
  try {
    localStorage.removeItem(NOTICE);
  } catch {
    /* nothing to forget */
  }
}
</script>

<template>
  <div v-if="installed" class="mt-3 border-l-2 border-lac pl-3 text-[0.9rem] text-papier" role="status">
    <div class="flex items-start gap-3">
      <p class="flex-1 break-words">
        <template v-if="installed.whats_new?.length">{{ t("app.notice.updated", { version: installed.version }) }} </template>
        <template v-if="installed.file">{{ t("app.notice.downloaded", { version: installed.version, dir: installed.dir, file: installed.file }) }}</template>
      </p>
      <button type="button" class="shrink-0 rounded border border-courbe-fonce px-2 text-courbe hover:text-papier" @click="close">
        {{ t("app.notice.close") }}
      </button>
    </div>
    <details v-if="installed.whats_new?.length" class="mt-1">
      <summary class="cursor-pointer text-courbe underline-offset-4 hover:underline">{{ t("app.notice.whats_new") }}</summary>
      <WhatsNew :releases="installed.whats_new" class="mt-2" />
    </details>
  </div>
</template>
