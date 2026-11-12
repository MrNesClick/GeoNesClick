<script setup lang="ts">
// After the round: "Where was it?". Grows the test set and tracks your progress: missed countries, and
// above all your confusions (real country taken for another) with the metas that tell them apart.
import { computed, ref, watch } from "vue";
import { i18n, t } from "../i18n";
import type { Analysis, Progress } from "../engine";
import { countryName, engine, flag, num, labelCapture, previewTruth } from "../engine";

const props = defineProps<{ analysis: Analysis; countries: string[]; progress: Progress | null }>();

const country = ref("");
const guessed = ref("");
const found = ref<boolean | null>(null); // if the answered country is not asked for (setting)
// Google Maps link of the real place (GeoGuessr end screen): the bench then measures region and accuracy in km.
const link = ref("");
const truth = ref<{ lat: number; lon: number; country: string; region_name: string } | null>(null);
const truthError = ref("");
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => props.analysis.id,
  () => {
    country.value = "";
    guessed.value = "";
    found.value = null;
    link.value = "";
    truth.value = null;
    truthError.value = "";
  },
);
watch(link, (value) => {
  clearTimeout(timer);
  truth.value = null;
  truthError.value = "";
  if (!value.trim()) return;
  timer = setTimeout(async () => {
    const r = await previewTruth(value);
    if (value !== link.value) return; // a more recent input wins
    if ("error" in r) truthError.value = r.error;
    else {
      truth.value = r;
      if (r.country && props.countries.includes(r.country)) country.value = r.country;
    }
  }, 300);
});
const coords = (lat: number, lon: number) =>
  `${num(Math.abs(lat))}° ${t(lat >= 0 ? "coord.north" : "coord.south")}, ${num(Math.abs(lon))}° ${t(lon >= 0 ? "coord.east" : "coord.west")}`;

const sorted = computed(() =>
  [...props.countries].sort((a, b) => countryName(a).localeCompare(countryName(b), i18n.lang)),
);

// Countries to work on: those where you missed at least one round, most missed first.
const toWork = computed(() =>
  Object.entries(props.progress?.by_country ?? {})
    .filter(([, [n, ok]]) => ok < n)
    .sort(([, [n1, ok1]], [, [n2, ok2]]) => ok1 / n1 - ok2 / n2 || n2 - n1)
    .slice(0, 4),
);

async function save() {
  if (!country.value) return;
  const url = truth.value ? link.value : "";
  if (engine.dataset.ask_guessed) await labelCapture(props.analysis.id, country.value, guessed.value, null, url);
  else await labelCapture(props.analysis.id, country.value, "", found.value, url);
}

const field = "mt-1 w-full rounded-md border border-courbe-fonce bg-relief px-3 py-2 text-papier";
</script>

<template>
  <div>

    <p v-if="analysis.labelled" class="text-papier" role="status">
      {{ t("label.added") }}
      <span aria-hidden="true">{{ flag(analysis.labelled.country) }}</span>
      {{ countryName(analysis.labelled.country) }}.
      <template v-if="analysis.labelled.found === true">{{ t("label.found") }}</template>
      <template v-else-if="analysis.labelled.guessed">
        {{ t("label.you_answered_country", { country: countryName(analysis.labelled.guessed) }) }}
      </template>
      <button type="button" class="ml-1 text-[0.85rem] text-courbe underline underline-offset-4 hover:text-papier" @click="analysis.labelled = null">
        {{ t("label.correct") }}
      </button>
    </p>

    <form v-else class="space-y-3" @submit.prevent="save">
      <label class="block">
        <span class="text-[0.85rem] text-courbe">{{ t("label.link") }}</span>
        <input v-model="link" type="url" autocomplete="off" :class="field" placeholder="https://www.google.com/maps/@…" />
        <span v-if="truth" class="mt-1 block text-[0.85rem] text-papier">
          → {{ truth.country ? `${flag(truth.country)} ${countryName(truth.country)}` : t("label.at_sea") }}<template
            v-if="truth.region_name"> › {{ truth.region_name }}</template> · {{ coords(truth.lat, truth.lon) }}
        </span>
        <span v-else-if="truthError" class="mt-1 block text-[0.85rem] text-alerte">{{ truthError }}</span>
        <span v-else class="mt-1 block text-[0.8rem] text-courbe">
          {{ t("label.link_help") }}
        </span>
      </label>
      <label class="block">
        <span class="text-[0.85rem] text-courbe">{{ t("label.right_country") }}</span>
        <select v-model="country" :class="field">
          <option value="" disabled>{{ t("label.choose_country") }}</option>
          <option v-for="c in sorted" :key="c" :value="c">{{ countryName(c) }}</option>
        </select>
      </label>

      <label v-if="engine.dataset.ask_guessed" class="block">
        <span class="text-[0.85rem] text-courbe">{{ t("label.you_answered") }}</span>
        <select v-model="guessed" :class="field">
          <option value="">{{ t("label.dont_remember") }}</option>
          <option v-for="c in sorted" :key="c" :value="c">{{ countryName(c) }}</option>
        </select>
      </label>

      <fieldset v-else class="flex flex-wrap gap-2">
        <legend class="mb-1 text-[0.85rem] text-courbe">{{ t("label.had_found") }}</legend>
        <label
          v-for="opt in [{ v: true, text: t('label.yes') }, { v: false, text: t('label.no') }]"
          :key="String(opt.v)"
          class="cursor-pointer rounded-md border px-3 py-1.5"
          :class="found === opt.v ? 'border-papier text-papier' : 'border-courbe-fonce text-courbe'"
        >
          <input v-model="found" type="radio" name="found" :value="opt.v" class="sr-only" />
          {{ opt.text }}
        </label>
      </fieldset>

      <button
        type="submit"
        class="rounded-md bg-papier px-4 py-2 font-bold text-encre hover:bg-white disabled:opacity-40"
        :disabled="!country || engine.busy"
      >
        {{ t("label.save") }}
      </button>
    </form>

    <div v-if="progress && progress.rounds" class="mt-4 space-y-1 text-[0.9rem] text-courbe">
      <p>
        <span class="text-papier">{{ t("label.progress_found", { found: progress.found, rounds: progress.rounds }) }}</span>
        <template v-if="progress.model_rounds">
          {{ t("label.progress_model", { top1: progress.model_top1, rounds: progress.model_rounds }) }}
        </template>
      </p>
      <p v-if="toWork.length">
        {{ t("label.to_work") }}
        <template v-for="([code, [n, ok]], i) in toWork" :key="code">
          <span v-if="i">, </span>
          <span class="text-papier"><span aria-hidden="true">{{ flag(code) }}</span> {{ countryName(code) }}</span>
          ({{ ok }}/{{ n }})
        </template>
      </p>
    </div>

    <div v-if="progress?.confusions?.length" class="mt-5">
      <h3 class="text-[0.9rem] font-bold text-papier">{{ t("label.confusions") }}</h3>
      <ul class="mt-2 space-y-4">
        <li v-for="c in progress.confusions" :key="c.country + c.guessed">
          <p class="text-papier">
            <span aria-hidden="true">{{ flag(c.country) }}</span> {{ countryName(c.country) }}
            <span class="text-courbe">{{ t("label.taken_for") }}</span>
            <span aria-hidden="true">{{ flag(c.guessed) }}</span> {{ countryName(c.guessed) }}
            <span class="tabular-nums text-courbe">× {{ c.count }}</span>
          </p>
          <div v-for="lf in c.lookfor" :key="lf.category" class="mt-1.5 border-l-2 border-foret/50 pl-3 text-[0.9rem]">
            <p class="text-foret">{{ lf.label }}</p>
            <p v-for="h in lf.hints" :key="h.hint" class="text-papier">
              <span aria-hidden="true" class="mr-1.5 tracking-wider"><span v-for="code in h.countries" :key="code">{{ flag(code) }}</span></span>
              <span class="sr-only">{{ t("summary.label_colon", { label: h.countries.map(countryName).join(", ") }) }}</span>
              {{ h.hint }}
            </p>
          </div>
          <p v-if="!c.lookfor.length" class="mt-1 text-[0.85rem] text-courbe">
            {{ t("label.no_meta_yet") }}
          </p>
        </li>
      </ul>
    </div>
  </div>
</template>
