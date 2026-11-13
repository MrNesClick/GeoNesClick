<script setup lang="ts">
// What the coach says about its version, one line at a time, never pushing the analysis down:
// - a newer version out (engine updates.py): "Later" closes it for that version (Settings › General keeps saying it);
// - after an installation or an update (Setup.vue, placeApp): one line whose button opens a panel over the coach with
//   what changed, where GeoNesClick is installed and the downloaded file that may now be deleted;
// - then, once, that the update check is on, for whoever did not choose it in the installer (an update from 0.4.x).
import { computed, nextTick, ref } from "vue";
import { dismissUpdate, engine, openRelease } from "../engine";
import { t } from "../i18n";
import WhatsNew, { type Release } from "./WhatsNew.vue";

interface Installed { version: string; dir: string; file: string | null; whats_new?: Release[] }
const NOTICE = "geonesclick.notice";
/** Set by the installer, where the option was shown: the note is for those who never saw it. */
const TOLD = "geonesclick.updates_told";

function read(): Installed | null {
  try {
    const saved = JSON.parse(localStorage.getItem(NOTICE) ?? "null");
    return saved && typeof saved.dir === "string" && (typeof saved.file === "string" || saved.whats_new?.length) ? saved : null;
  } catch {
    return null; // storage unavailable or damaged: no note
  }
}
function remember(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* not remembered: the note may come back once */
  }
}

const installed = ref(read());
const updated = computed(() => !!installed.value?.whats_new?.length);
const panel = ref(false);
const closeButton = ref<HTMLButtonElement | null>(null);
async function openPanel() {
  panel.value = true;
  await nextTick();
  closeButton.value?.focus();
}
function closeInstalled() {
  panel.value = false;
  installed.value = null;
  remember(NOTICE, null);
}

const told = ref(true);
try {
  told.value = localStorage.getItem(TOLD) === "1";
} catch {
  /* storage unavailable: the note is not shown rather than shown at every start */
}
// After the installation's line, not with it: one line at a time.
const updatesNote = computed(() => !installed.value && !told.value && engine.updates.enabled);
function closeUpdatesNote() {
  told.value = true;
  remember(TOLD, "1");
}

const banner = computed(() => (engine.updates.latest && !engine.updates.dismissed ? engine.updates.latest : ""));

const line = "mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 border-l-2 border-lac pl-3 text-[0.9rem] text-papier";
const button = "rounded border border-courbe-fonce px-2 text-papier hover:bg-relief";
const quiet = "rounded border border-courbe-fonce px-2 text-courbe hover:text-papier";
</script>

<template>
  <div v-if="banner" :class="line" role="status">
    <span class="flex-1">{{ t("app.update.banner", { latest: banner }) }}</span>
    <button type="button" :class="button" @click="openRelease(engine.updates.url)">{{ t("updates.open") }}</button>
    <button type="button" :class="quiet" @click="dismissUpdate(banner)">{{ t("app.update.later") }}</button>
  </div>

  <div v-if="installed" :class="line" role="status">
    <span class="flex-1">{{ t(updated ? "app.notice.updated_line" : "app.notice.installed_line", { version: installed.version }) }}</span>
    <button type="button" :class="button" @click="openPanel">{{ t(updated ? "app.notice.whats_new" : "app.notice.details") }}</button>
    <button type="button" :class="quiet" @click="closeInstalled">{{ t("app.notice.close") }}</button>
  </div>

  <div v-else-if="updatesNote" :class="line" role="status">
    <span class="flex-1">{{ t("app.notice.updates_on") }}</span>
    <button type="button" :class="quiet" @click="closeUpdatesNote">{{ t("app.notice.close") }}</button>
  </div>

  <!-- Over the coach, never inside its column: the analysis stays where it is. -->
  <Teleport to="body">
    <!-- Above the tab bar (z-[1100], App.vue) and the map's attribution (z-[1000]). -->
    <div v-if="panel && installed" class="fixed inset-0 z-[1200] flex flex-col bg-encre px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
         role="dialog" aria-modal="true" aria-labelledby="installed-title" @keydown.esc="panel = false">
      <div class="flex items-baseline justify-between gap-3 border-b border-courbe-fonce pb-2">
        <h2 id="installed-title" class="text-[1.2rem] font-bold text-papier">{{ t("app.notice.panel_title", { version: installed.version }) }}</h2>
        <button ref="closeButton" type="button" :class="quiet" @click="panel = false">{{ t("app.notice.close_panel") }}</button>
      </div>
      <!-- pr-3: the text keeps away from the scroll bar; pb-6: the last line does not touch the bottom edge. -->
      <div class="min-h-0 flex-1 overflow-y-auto pt-3 pr-3 pb-6 text-[0.95rem]">
        <WhatsNew v-if="installed.whats_new?.length" :releases="installed.whats_new" />
        <div class="mt-5 space-y-3 border-t border-courbe-fonce pt-4 text-papier">
          <p>{{ t("app.notice.installed_in", { dir: installed.dir }) }}</p>
          <div v-if="installed.file">
            <p>{{ t("app.notice.delete_file") }}</p>
            <code class="mt-1 block break-all rounded bg-relief px-2 py-1 text-[0.9rem] text-papier select-all">{{ installed.file }}</code>
          </div>
          <p v-if="!told && engine.updates.enabled" class="text-courbe">{{ t("app.notice.updates_on") }}</p>
        </div>
      </div>
    </div>
  </Teleport>
</template>
