<script setup lang="ts">
// Head of Settings › General: the version, the newer one if any (also after its banner was closed), "Check" and the
// automatic check on or off ([updates] check).
import { computed, ref } from "vue";
import { checkUpdates, engine, openRelease, saveSettings } from "../engine";
import { i18n, t } from "../i18n";

const checking = ref(false);
const saveError = ref("");
const u = computed(() => engine.updates);
const when = computed(() => (u.value.checked ? new Date(u.value.checked).toLocaleDateString(i18n.lang, { dateStyle: "medium" }) : ""));

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

const button = "rounded-md border border-courbe-fonce px-2 py-0.5 text-papier hover:bg-relief disabled:opacity-40";
</script>

<template>
  <div role="group" :aria-label="t('updates.title')" class="space-y-2">
    <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span class="font-bold text-papier">{{ t("updates.version", { version: u.current }) }}</span>
      <span aria-hidden="true" class="text-courbe">·</span>
      <span v-if="u.latest" class="text-alerte">{{ t("updates.available", { latest: u.latest }) }}</span>
      <span v-else-if="u.error" class="text-alerte">{{ t("updates.failed", { error: u.error }) }}</span>
      <span v-else class="text-courbe">{{ when ? t("updates.up_to_date", { when }) : t("updates.never") }}</span>
      <button v-if="u.latest" type="button" :class="button" @click="openRelease(u.url)">{{ t("updates.open") }}</button>
      <button type="button" :class="button" :disabled="checking" @click="checkNow">
        {{ checking ? t("updates.checking") : t("updates.check_now") }}
      </button>
    </p>
    <label class="flex items-start gap-3">
      <input type="checkbox" class="mt-1 h-4 w-4 shrink-0 accent-lac" :checked="u.enabled"
             @change="toggle(($event.target as HTMLInputElement).checked)" />
      <span>
        <span class="text-papier">{{ t("setting.updates.check") }}</span>
        <span class="block text-[0.85rem] text-courbe">{{ t("setting.updates.check.hint") }}</span>
      </span>
    </label>
    <p v-if="saveError" class="text-alerte" role="alert">{{ saveError }}</p>
  </div>
</template>
