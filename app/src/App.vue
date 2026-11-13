<script setup lang="ts">
import { computed, ref, watch } from "vue";
import Activity from "./components/Activity.vue";
import CoachMap from "./components/CoachMap.vue";
import Countries from "./components/Countries.vue";
import HelpLevel from "./components/HelpLevel.vue";
import LabelForm from "./components/LabelForm.vue";
import Locks from "./components/Locks.vue";
import LookHere from "./components/LookHere.vue";
import Marks from "./components/Marks.vue";
import Notices from "./components/Notices.vue";
import MetaHints from "./components/MetaHints.vue";
import Observations from "./components/Observations.vue";
import PlonkitTips from "./components/PlonkitTips.vue";
import Section from "./components/Section.vue";
import SettingsPanel from "./components/SettingsPanel.vue";
import Summary from "./components/Summary.vue";
import { countryName, engine, flag, lockedCountry, requestCapture, requestFreeze, reselectWindow, tipsByCountry } from "./engine";
import { t } from "./i18n";
import * as sum from "./summaries";

const status = computed(() => {
  if (!engine.connected) return { tone: "bg-courbe", text: t("app.status.starting") };
  if (engine.capture.starting) return { tone: "bg-courbe", text: t("app.status.pick_window") };
  if (!engine.capture.alive) return { tone: "bg-alerte", text: engine.capture.message };
  if (!engine.streetclip.ready) return { tone: "bg-courbe", text: t("app.status.loading_model") };
  return { tone: "bg-foret", text: engine.marks.enabled ? t("app.status.ready_marks") : t("app.status.ready") };
});
// Window views: the coach, the full-size map (level 3 and up), the settings.
const view = ref<"coach" | "map" | "settings">("coach");
const showSettings = computed(() => view.value === "settings");
const level = computed(() => engine.helpLevel);
const mapAvailable = computed(() => engine.map.enabled && level.value >= 3);
watch(mapAvailable, (ok) => {
  if (!ok && view.value === "map") view.value = "coach"; // map hidden at levels 1 and 2: nothing to reveal
});
// New zones ready but not seen yet: a dot on the Map tab (background work shows).
const mapUnseen = ref(false);
watch(
  () => [engine.current?.id, engine.current?.cloud.status],
  () => {
    if (engine.current?.cloud.status === "done" && view.value !== "map") mapUnseen.value = true;
    if (engine.current?.cloud.status !== "done") mapUnseen.value = false;
  },
);
watch(view, (v) => {
  if (v === "map") mapUnseen.value = false;
});
// Bottom tab bar: navigation; the help levels, at the top, set how much help is given.
const tabs = computed(() => [
  { id: "coach" as const, label: t("app.tab.coach"), disabled: false, hint: "" },
  ...(engine.map.enabled
    ? [{ id: "map" as const, label: t("app.tab.map"), disabled: !mapAvailable.value || !engine.current,
         hint: !mapAvailable.value ? t("app.tab.map_level") : engine.current ? "" : t("app.need_capture") }]
    : []),
  { id: "settings" as const, label: t("app.tab.settings"), disabled: false, hint: "" },
]);
</script>

<template>
  <!-- The map uses the full width when the window is maximised; the coach stays a readable column. -->
  <div class="mx-auto flex min-h-screen flex-col px-4 pt-4" :class="view === 'map' ? 'max-w-none' : 'max-w-xl'">
    <header class="flex items-center gap-3 border-b border-courbe-fonce pb-3">
      <span class="size-2.5 shrink-0 rounded-full" :class="status.tone" aria-hidden="true" />
      <p class="min-w-0 flex-1 truncate text-[0.9rem] text-courbe" role="status">{{ status.text }}</p>
      <button
        v-if="engine.connected && !engine.capture.alive && !engine.capture.starting"
        type="button"
        class="shrink-0 rounded-md border border-alerte/60 px-3 py-1.5 text-[0.9rem] text-papier hover:bg-alerte/10 disabled:opacity-50"
        :disabled="engine.busy"
        @click="reselectWindow"
      >
        {{ t("app.restart_sharing") }}
      </button>
      <template v-else>
        <button
          v-if="engine.marks.enabled"
          type="button"
          class="shrink-0 rounded-md border border-marque/70 px-3 py-1.5 text-[0.9rem] text-papier hover:bg-marque/10 disabled:opacity-40"
          :title="engine.current ? t('app.mark.hint') : t('app.mark.need_capture')"
          :disabled="!engine.connected || !engine.capture.alive || engine.busy || !engine.current"
          @click="requestFreeze"
        >
          {{ t("app.mark") }}
        </button>
        <button
          type="button"
          class="shrink-0 rounded-md bg-papier px-3 py-1.5 text-[0.9rem] font-bold text-encre hover:bg-white disabled:opacity-40"
          :disabled="!engine.connected || !engine.capture.alive || engine.busy"
          @click="requestCapture"
        >
          {{ t("app.capture") }}
        </button>
      </template>
    </header>

    <HelpLevel v-if="!showSettings" />
    <Activity v-if="!showSettings" />

    <p v-if="engine.error" class="mt-3 border-l-2 border-alerte pl-3 text-[0.9rem] text-papier" role="alert">
      {{ engine.error }}
    </p>
    <Notices />

    <main v-if="showSettings" class="flex-1">
      <SettingsPanel />
    </main>

    <main v-else-if="view === 'map' && engine.current && mapAvailable" class="flex min-h-0 flex-1 flex-col pt-3">
      <CoachMap :key="engine.current.id" :analysis="engine.current" :level="level" />
    </main>

    <main v-else-if="engine.current" class="flex-1">
      <!-- Locks: at the top, outside the collapsible sections (they narrow down everything that follows). -->
      <Locks v-if="engine.locks.enabled" :analysis="engine.current" />
      <Transition name="arrival" appear mode="out-in">
        <div :key="engine.current.id" class="pt-2">
          <!-- Sections in order of usefulness; each one's summary stays readable when it is collapsed. -->
          <Section v-if="level >= 4" id="answer" :title="t('app.section.answer')" tone="papier" :summary="sum.answer(engine.current)">
            <Summary :analysis="engine.current" />
          </Section>

          <!-- The marks are your proof: right after the answer, at every level (they name no country). -->
          <Section v-if="engine.current.marks.length" id="marks" :title="t('app.section.marks')" tone="papier" :summary="sum.marks(engine.current)">
            <Marks :marks="engine.current.marks" :analysis-id="engine.current.id" :verdict="engine.current.verdict" />
          </Section>

          <Section id="capture" :title="t('app.section.capture')" :open="false" tone="papier" :summary="sum.capture(engine.current)">
            <img :src="engine.current.thumbnail" :alt="t('app.capture_alt')" class="w-full rounded-md border border-courbe-fonce" />
            <p v-if="engine.current.guessedCrop" class="mt-1 text-[0.85rem] text-courbe">{{ t("app.crop_guessed") }}</p>
            <p v-for="w in engine.current.warnings" :key="w" class="mt-1 text-[0.85rem] text-alerte">{{ t(sum.WARNING_TEXT[w]) }}</p>
          </Section>

          <Section v-if="level < 3" id="look-here" :title="t('app.section.look_here')" :summary="sum.metas(engine.current)">
            <LookHere :lookfor="engine.current.lookfor" />
          </Section>

          <template v-else>
            <Section id="countries" :title="t('app.section.countries')" :summary="sum.countries(engine.current)">
              <Countries :analysis="engine.current" />
            </Section>
            <Section id="tiebreak" :title="t('app.section.tiebreak')"
                     :summary="lockedCountry(engine.current) ? t('app.country_locked') : sum.metas(engine.current)">
              <p v-if="lockedCountry(engine.current)" class="text-[0.9rem] text-courbe">
                {{ t("app.country_locked.detail", { country: `${flag(lockedCountry(engine.current)!)} ${countryName(lockedCountry(engine.current)!)}` }) }}
              </p>
              <MetaHints v-else :lookfor="engine.current.lookfor" />
            </Section>
            <Section
              v-if="tipsByCountry(engine.current).length"
              id="tips"
              :title="t('app.section.tips')"
              :open="false"
              :summary="sum.tips(engine.current)"
            >
              <PlonkitTips :analysis="engine.current" />
            </Section>
            <!-- First launch on a processor: the tips are still being encoded (minutes); say so instead of nothing. -->
            <Section
              v-else-if="engine.plonkit.enabled && engine.plonkit.status === 'busy'"
              id="tips"
              :title="t('app.section.tips')"
              :open="false"
              :summary="engine.plonkit.message"
            >
              <p class="text-[0.9rem] text-courbe" role="status">{{ t("tips.preparing") }}</p>
            </Section>
          </template>

          <Section v-if="level >= 2" id="vision" :title="t('app.section.vision')" tone="lac" :open="level === 2" :summary="sum.vision(engine.current)">
            <Observations :vision="engine.current.vision" />
          </Section>

          <Section v-if="engine.dataset.enabled" id="round" :title="t('app.section.round')" :open="false" :summary="sum.round(engine.current)">
            <LabelForm :analysis="engine.current" :countries="engine.countries" :progress="engine.progress" />
          </Section>
        </div>
      </Transition>
    </main>

    <main v-else class="flex flex-1 flex-col justify-center py-10">
      <p class="atlas text-[1.6rem] leading-snug text-papier">{{ t("app.welcome.title") }}</p>
      <p class="mt-3 max-w-[34ch] text-courbe">
        {{ t("app.welcome.capture_before") }} <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">{{ t("key.super") }}</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">{{ t("key.shift") }}</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">G</kbd>{{ t("app.welcome.capture_after") }}
      </p>
      <p v-if="engine.marks.enabled" class="mt-3 max-w-[34ch] text-courbe">
        {{ t("app.welcome.mark_before") }} <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">{{ t("key.super") }}</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">{{ t("key.shift") }}</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">Z</kbd>
        {{ t("app.welcome.mark_after") }}
      </p>
    </main>

    <nav
      class="sticky bottom-0 z-[1100] -mx-4 mt-6 grid border-t border-courbe-fonce bg-encre px-2 pb-[env(safe-area-inset-bottom)]"
      :style="{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }"
      :aria-label="t('app.tabs_label')"
    >
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        class="border-t-2 py-2.5 text-[0.95rem] font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-40 motion-reduce:transition-none"
        :class="view === tab.id ? 'border-papier text-papier' : 'border-transparent text-courbe hover:text-papier'"
        :aria-current="view === tab.id ? 'page' : undefined"
        :disabled="tab.disabled"
        :title="tab.hint"
        @click="view = tab.id"
      >
        {{ tab.label }}<span
          v-if="tab.id === 'map' && mapUnseen && !tab.disabled"
          class="ml-1.5 inline-block size-2 rounded-full bg-lac align-middle"
          :aria-label="t('app.new_zones')"
        />
      </button>
    </nav>
  </div>
</template>
