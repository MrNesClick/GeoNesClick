<script setup lang="ts">
// Top of the Settings, always open: the version, the newer one if any (also after its banner was closed), "Check now"
// and the automatic check on or off ([updates] check).
import { computed, ref } from "vue";
import { checkUpdates, engine, openRelease, saveSettings } from "../engine";
import { i18n, t } from "../i18n";

const checking = ref(false);
const saveError = ref("");
const u = computed(() => engine.updates);
const when = computed(() => (u.value.checked ? new Date(u.value.checked).toLocaleString(i18n.lang, { dateStyle: "medium", timeStyle: "short" }) : ""));

async function checkNow() {
  checking.value = true;
  try {
    await checkUpdates();
  } finally {
    checking.value = false;
  }
}

async function toggle(on: boolean) {
  saveError.value = (await saveSettings({ updates: { check: on } })) ?? "";
}

const button = "rounded-md border border-courbe-fonce px-3 py-1 text-papier hover:bg-relief disabled:opacity-40";
</script>

<template>
  <section aria-labelledby="updates-title" class="mb-4 rounded-md border border-courbe-fonce px-3 py-2 text-[0.95rem]">
    <h3 id="updates-title" class="font-bold text-papier">{{ t("updates.title") }}</h3>
    <p class="mt-1 text-papier">{{ t("updates.version", { version: u.current }) }}</p>
    <p v-if="u.latest" class="mt-1 flex flex-wrap items-center gap-2 text-papier">
      <span>{{ t("updates.available", { latest: u.latest }) }}</span>
      <button type="button" :class="button" @click="openRelease(u.url)">{{ t("updates.open") }}</button>
    </p>
    <p v-else-if="u.error" class="mt-1 text-alerte">{{ t("updates.failed", { error: u.error }) }}</p>
    <p v-else class="mt-1 text-courbe">{{ when ? t("updates.up_to_date", { when }) : t("updates.never") }}</p>
    <button type="button" :class="button" class="mt-2" :disabled="checking" @click="checkNow">
      {{ checking ? t("updates.checking") : t("updates.check_now") }}
    </button>
    <label class="mt-3 flex items-start gap-3">
      <input type="checkbox" class="mt-1 h-4 w-4 shrink-0 accent-lac" :checked="u.enabled"
             @change="toggle(($event.target as HTMLInputElement).checked)" />
      <span>
        <span class="text-papier">{{ t("setting.updates.check") }}</span>
        <span class="block text-courbe">{{ t("setting.updates.check.hint") }}</span>
      </span>
    </label>
    <p v-if="saveError" class="mt-1 text-alerte" role="alert">{{ saveError }}</p>
  </section>
</template>
