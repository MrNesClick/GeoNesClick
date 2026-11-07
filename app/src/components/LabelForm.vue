<script setup lang="ts">
// Après la manche : « C'était où ? ». Enrichit le jeu de test et suit ta progression : pays ratés, et
// surtout tes confusions (pays réel pris pour un autre) avec les metas qui les séparent.
import { computed, ref, watch } from "vue";
import type { Analysis, Progress } from "../engine";
import { countryName, engine, flag, labelCapture } from "../engine";

const props = defineProps<{ analysis: Analysis; countries: string[]; progress: Progress | null }>();

const country = ref("");
const guessed = ref("");
const found = ref<boolean | null>(null); // si le pays répondu n'est pas demandé (réglage)
watch(
  () => props.analysis.id,
  () => {
    country.value = "";
    guessed.value = "";
    found.value = null;
  },
);

const sorted = computed(() =>
  [...props.countries].sort((a, b) => countryName(a).localeCompare(countryName(b), "fr")),
);

// Pays à retravailler : ceux où tu as raté au moins une manche, du plus raté au moins raté.
const toWork = computed(() =>
  Object.entries(props.progress?.by_country ?? {})
    .filter(([, [n, ok]]) => ok < n)
    .sort(([, [n1, ok1]], [, [n2, ok2]]) => ok1 / n1 - ok2 / n2 || n2 - n1)
    .slice(0, 4),
);

async function save() {
  if (!country.value) return;
  if (engine.dataset.ask_guessed) await labelCapture(props.analysis.id, country.value, guessed.value);
  else await labelCapture(props.analysis.id, country.value, "", found.value);
}

const field = "mt-1 w-full rounded-md border border-courbe-fonce bg-relief px-3 py-2 text-papier";
</script>

<template>
  <div>

    <p v-if="analysis.labelled" class="text-papier" role="status">
      Ajouté au jeu de test :
      <span aria-hidden="true">{{ flag(analysis.labelled.country) }}</span>
      {{ countryName(analysis.labelled.country) }}.
      <template v-if="analysis.labelled.found === true">Bien trouvé.</template>
      <template v-else-if="analysis.labelled.guessed">
        Tu avais répondu {{ countryName(analysis.labelled.guessed) }}.
      </template>
      <button type="button" class="ml-1 text-[0.85rem] text-courbe underline underline-offset-4 hover:text-papier" @click="analysis.labelled = null">
        Corriger
      </button>
    </p>

    <form v-else class="space-y-3" @submit.prevent="save">
      <label class="block">
        <span class="text-[0.85rem] text-courbe">Pays de la bonne réponse</span>
        <select v-model="country" :class="field">
          <option value="" disabled>Choisis le pays</option>
          <option v-for="c in sorted" :key="c" :value="c">{{ countryName(c) }}</option>
        </select>
      </label>

      <label v-if="engine.dataset.ask_guessed" class="block">
        <span class="text-[0.85rem] text-courbe">Tu avais répondu</span>
        <select v-model="guessed" :class="field">
          <option value="">Je ne sais plus</option>
          <option v-for="c in sorted" :key="c" :value="c">{{ countryName(c) }}</option>
        </select>
      </label>

      <fieldset v-else class="flex flex-wrap gap-2">
        <legend class="mb-1 text-[0.85rem] text-courbe">Tu l'avais trouvé ?</legend>
        <label
          v-for="opt in [{ v: true, t: 'Oui' }, { v: false, t: 'Non' }]"
          :key="opt.t"
          class="cursor-pointer rounded-md border px-3 py-1.5"
          :class="found === opt.v ? 'border-papier text-papier' : 'border-courbe-fonce text-courbe'"
        >
          <input v-model="found" type="radio" name="found" :value="opt.v" class="sr-only" />
          {{ opt.t }}
        </label>
      </fieldset>

      <button
        type="submit"
        class="rounded-md bg-papier px-4 py-2 font-bold text-encre hover:bg-white disabled:opacity-40"
        :disabled="!country || engine.busy"
      >
        Enregistrer
      </button>
    </form>

    <div v-if="progress && progress.rounds" class="mt-4 space-y-1 text-[0.9rem] text-courbe">
      <p>
        Tu as trouvé <span class="text-papier">{{ progress.found }} pays sur {{ progress.rounds }}</span>.
        <template v-if="progress.model_rounds">
          StreetCLIP avait vu juste {{ progress.model_top1 }} fois sur {{ progress.model_rounds }}.
        </template>
      </p>
      <p v-if="toWork.length">
        À retravailler :
        <template v-for="([code, [n, ok]], i) in toWork" :key="code">
          <span v-if="i">, </span>
          <span class="text-papier"><span aria-hidden="true">{{ flag(code) }}</span> {{ countryName(code) }}</span>
          ({{ ok }}/{{ n }})
        </template>
      </p>
    </div>

    <div v-if="progress?.confusions?.length" class="mt-5">
      <h3 class="text-[0.9rem] font-bold text-papier">Tes confusions</h3>
      <ul class="mt-2 space-y-4">
        <li v-for="c in progress.confusions" :key="c.country + c.guessed">
          <p class="text-papier">
            <span aria-hidden="true">{{ flag(c.country) }}</span> {{ countryName(c.country) }}
            <span class="text-courbe">prise pour</span>
            <span aria-hidden="true">{{ flag(c.guessed) }}</span> {{ countryName(c.guessed) }}
            <span class="tabular-nums text-courbe">× {{ c.count }}</span>
          </p>
          <div v-for="lf in c.lookfor" :key="lf.category" class="mt-1.5 border-l-2 border-foret/50 pl-3 text-[0.9rem]">
            <p class="text-foret">{{ lf.label }}</p>
            <p v-for="h in lf.hints" :key="h.hint" class="text-papier">
              <span aria-hidden="true" class="mr-1.5 tracking-wider"><span v-for="code in h.countries" :key="code">{{ flag(code) }}</span></span>
              <span class="sr-only">{{ h.countries.map(countryName).join(", ") }} :</span>
              {{ h.hint }}
            </p>
          </div>
          <p v-if="!c.lookfor.length" class="mt-1 text-[0.85rem] text-courbe">
            Aucune meta ne sépare encore ces deux pays : ajoute la tienne dans mes-metas.toml.
          </p>
        </li>
      </ul>
    </div>
  </div>
</template>
