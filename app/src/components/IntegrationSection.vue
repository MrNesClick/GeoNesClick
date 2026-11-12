<script setup lang="ts">
// Settings group "GNOME integration": the keyboard shortcuts and the applications-menu entry (icon in the dock).
// Not in config.toml: their state is read from the system and changed through Tauri (src-tauri/src/integration.rs).
import { computed, onMounted, reactive, ref, watch } from "vue";
import { engine } from "../engine";
import type { Key } from "../i18n";
import { t } from "../i18n";
import Section from "./Section.vue";

interface Status { appimage: boolean; shortcuts: boolean | null; menu: boolean }
type Kind = "shortcuts" | "menu";

const state = ref<Status | null>(null);
const status = reactive<Partial<Record<Kind, { tone: "ok" | "error" | "busy"; text: string }>>>({});
const COMMAND: Record<Kind, string> = { shortcuts: "set_shortcuts", menu: "set_menu_entry" };
const LABEL: Record<Kind, [Key, Key]> = {
  shortcuts: ["setup.shortcuts", "setup.shortcuts.detail"],
  menu: ["setup.menu", "setup.menu.detail"],
};

async function invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T> {
  const core = await import("@tauri-apps/api/core");
  return core.invoke<T>(cmd, args);
}
async function load() {
  state.value = await invoke<Status>("integration_status").catch(() => null);
}
onMounted(load);
// After an uninstall ("Erase everything"), both are gone: the group shows it, and nothing can be added back (the
// shortcuts would point to the removed engine).
watch(() => engine.uninstalled, (gone) => gone && void load());

async function set(kind: Kind, on: boolean) {
  status[kind] = { tone: "busy", text: t("settings.saving") };
  const error = await invoke(COMMAND[kind], { on }).then(() => null, (e) => String(e));
  await load(); // the screen shows what is actually in place
  status[kind] = error ? { tone: "error", text: error } : { tone: "ok", text: t("settings.saved") };
  if (!error) setTimeout(() => delete status[kind], 2500);
}

const value = (kind: Kind) => (kind === "shortcuts" ? state.value?.shortcuts : state.value?.menu);
const disabled = (kind: Kind) =>
  engine.uninstalled || !state.value?.appimage || (kind === "shortcuts" && state.value.shortcuts === null);
const summary = computed(() => {
  const s = state.value;
  if (!s) return "";
  return [s.shortcuts === null ? "" : t(s.shortcuts ? "settings.sum.shortcuts_on" : "settings.sum.shortcuts_off"),
          t(s.menu ? "settings.sum.menu_on" : "settings.sum.menu_off")].filter(Boolean).join(" · ");
});
const check = "mt-1 size-4 shrink-0 accent-[var(--color-foret)] disabled:opacity-50";
const TONE = { ok: "text-foret", error: "text-alerte", busy: "text-courbe" };
</script>

<template>
  <Section id="setting-integration" :title="t('group.integration')" :summary="summary" :open="false" tone="papier">
    <div class="space-y-5 py-1">
      <p v-if="state && !state.appimage" class="text-[0.85rem] text-courbe">{{ t("settings.integration.appimage_only") }}</p>
      <p v-else-if="state?.shortcuts === null" class="text-[0.85rem] text-courbe">{{ t("settings.integration.unreadable") }}</p>
      <div v-for="kind in (['shortcuts', 'menu'] as const)" :key="kind" :class="disabled(kind) ? 'opacity-60' : ''">
        <label class="flex items-start gap-3">
          <input :id="`setting-integration-${kind}`" type="checkbox" :class="check" :checked="!!value(kind)"
                 :disabled="disabled(kind) || status[kind]?.tone === 'busy'"
                 @change="set(kind, ($event.target as HTMLInputElement).checked)" />
          <span>{{ t(LABEL[kind][0]) }}<span class="block text-[0.85rem] text-courbe">{{ t(LABEL[kind][1]) }}</span></span>
        </label>
        <p v-if="status[kind]" class="mt-1 text-[0.85rem]" :class="TONE[status[kind]!.tone]" role="status">{{ status[kind]!.text }}</p>
      </div>
    </div>
  </Section>
</template>
