<script setup lang="ts">
// Notes the coach shows once, then never again: closed by the player, they are forgotten.
// - after an installation or an update (Setup.vue, placeApp): where GeoNesClick is installed, the downloaded AppImage
//   that may now be deleted, and for an update what changed since the previous version;
// - a newer version out (engine updates.py): a banner, closed for that version with "Later" (Settings keeps saying it);
// - the update check being on, for whoever did not choose it in the installer (an update from 0.4.x).
import { computed, ref } from "vue";
import { dismissUpdate, engine, openRelease } from "../engine";
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

/** Set by the installer, where the option was shown: the note is for those who never saw it. */
const TOLD = "geonesclick.updates_told";
const told = ref(true);
try {
  told.value = localStorage.getItem(TOLD) === "1";
} catch {
  /* storage unavailable: the note is not shown rather than shown at every start */
}
const updatesNote = computed(() => !told.value && engine.updates.enabled);
function closeUpdatesNote() {
  told.value = true;
  try {
    localStorage.setItem(TOLD, "1");
  } catch {
    /* not remembered: it may come back once */
  }
}
const banner = computed(() => (engine.updates.latest && !engine.updates.dismissed ? engine.updates.latest : ""));
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
  <div v-if="banner" class="mt-3 flex flex-wrap items-center gap-2 border-l-2 border-lac pl-3 text-[0.9rem] text-papier" role="status">
    <span class="flex-1">{{ t("app.update.banner", { latest: banner }) }}</span>
    <button type="button" class="rounded border border-courbe-fonce px-2 text-papier hover:bg-relief" @click="openRelease(engine.updates.url)">
      {{ t("updates.open") }}
    </button>
    <button type="button" class="rounded border border-courbe-fonce px-2 text-courbe hover:text-papier" @click="dismissUpdate(banner)">
      {{ t("app.update.later") }}
    </button>
  </div>
  <div v-if="updatesNote" class="mt-3 flex items-start gap-3 border-l-2 border-lac pl-3 text-[0.9rem] text-papier" role="status">
    <p class="flex-1">{{ t("app.notice.updates_on") }}</p>
    <button type="button" class="shrink-0 rounded border border-courbe-fonce px-2 text-courbe hover:text-papier" @click="closeUpdatesNote">
      {{ t("app.notice.close") }}
    </button>
  </div>
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
