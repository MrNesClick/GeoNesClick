<script setup lang="ts">
// Niveau 1, calculé en local : d'abord OÙ regarder (catégories d'indices qui départagent les pays
// probables), puis, à la demande, les pays eux-mêmes et l'indice propre à chacun.
import { computed } from "vue";
import type { CountryScore, LookFor, SimilarTip } from "../engine";
import { CATEGORY_LABELS, countryName, engine, flag, judgeHint, markdownSegments, openPlonkit } from "../engine";

const props = defineProps<{
  scores: CountryScore[] | null;
  lookfor: LookFor[] | null;
  similar: Record<string, SimilarTip[]> | null;
  ms: number | null;
  countriesShown: boolean;
}>();
const emit = defineEmits<{ showCountries: [] }>();

const pct = (p: number) => `${Math.round(p * 100)} %`;
const leader = computed(() => props.scores?.[0] ?? null);
const others = computed(() => props.scores?.slice(1) ?? []);
// Échelle réelle de 0 à 100 % sur un rail : la longueur se lit comme le pourcentage affiché.
const width = (p: number) => `${Math.max(1.5, p * 100)}%`;
// Astuces Plonk It qui ressemblent à la vue, dans l'ordre des pays probables.
const similarByCountry = computed(() =>
  (props.scores ?? [])
    .map((s) => ({ code: s.code, tips: props.similar?.[s.code] ?? [] }))
    .filter((c) => c.tips.length),
);
</script>

<template>
  <section aria-labelledby="n1-titre" class="text-foret">
    <header class="flex items-baseline justify-between gap-3">
      <h2 id="n1-titre" class="flex items-center gap-2 font-bold text-papier">
        <span class="grid size-6 place-items-center rounded-full border border-foret text-[0.8rem] text-foret" aria-label="Niveau">1</span>
        Où regarder
      </h2>
      <span v-if="ms !== null" class="text-[0.8rem] text-courbe">calcul local, {{ ms }} ms</span>
    </header>

    <p v-if="!scores" class="mt-3 text-courbe">Analyse de la vue en cours…</p>

    <template v-else>
      <!-- Sans spoiler : les catégories, par ordre d'utilité, et quoi y observer. -->
      <template v-if="!countriesShown">
        <ol v-if="lookfor?.length" class="mt-3 space-y-2.5">
          <li v-for="lf in lookfor" :key="lf.category" class="border-l-2 border-foret/60 pl-3">
            <span class="text-papier">{{ lf.label }}</span>
            <span v-for="look in lf.looks" :key="look" class="block text-[0.9rem] text-foret">
              Regarde {{ look }}.
            </span>
          </li>
        </ol>
        <p v-else class="mt-3 text-courbe">
          Aucune meta ne départage les pays probables de cette vue.
        </p>
        <button
          type="button"
          class="mt-4 w-full rounded-md border border-foret/40 px-4 py-3 text-left text-papier hover:border-foret hover:bg-foret/10"
          @click="emit('showCountries')"
        >
          Voir les pays probables et leurs indices
          <span class="block text-[0.85rem] text-courbe">Cherche d'abord ces indices dans la vue.</span>
        </button>
      </template>

      <template v-else-if="leader">
        <div class="mt-3">
          <p class="atlas text-[2rem] leading-tight font-semibold text-papier">
            <span aria-hidden="true" class="mr-2 not-italic">{{ flag(leader.code) }}</span>{{ countryName(leader.code) }}
          </p>
          <div class="mt-2 flex items-center gap-3">
            <div class="h-1.5 flex-1 rounded-full bg-courbe-fonce" aria-hidden="true">
              <div class="jauge h-full rounded-full bg-foret" :style="{ width: width(leader.probability) }" />
            </div>
            <span class="w-12 shrink-0 text-right tabular-nums text-papier">{{ pct(leader.probability) }}</span>
          </div>
        </div>

        <ol class="mt-4 space-y-2" aria-label="Autres candidats">
          <li v-for="s in others" :key="s.code" class="grid grid-cols-[8.5rem_1fr_3rem] items-center gap-3">
            <span class="atlas truncate text-papier/90">
              <span aria-hidden="true" class="mr-1.5 not-italic">{{ flag(s.code) }}</span>{{ countryName(s.code) }}
            </span>
            <div class="h-1 rounded-full bg-courbe-fonce" aria-hidden="true">
              <div class="jauge h-full rounded-full bg-foret/70" :style="{ width: width(s.probability) }" />
            </div>
            <span class="text-right tabular-nums text-courbe">{{ pct(s.probability) }}</span>
          </li>
        </ol>

        <div v-if="lookfor?.length" class="mt-5 space-y-4">
          <div v-for="lf in lookfor" :key="lf.category">
            <h3 class="text-[0.9rem] font-bold text-foret">{{ lf.label }}</h3>
            <ul class="mt-1.5 space-y-1.5">
              <li v-for="h in lf.hints" :key="h.hint" class="flex gap-2.5 text-[0.95rem]">
                <span class="shrink-0 tracking-wider" :title="h.countries.map(countryName).join(', ')">
                  <span v-for="c in h.countries" :key="c" aria-hidden="true">{{ flag(c) }}</span>
                  <span class="sr-only">{{ h.countries.map(countryName).join(", ") }}</span>
                </span>
                <span class="text-papier">
                  {{ h.hint }}
                  <span v-if="h.source === 'mes metas'" class="text-[0.8rem] text-foret">
                    {{ h.verified ? "(ta meta, vérifiée)" : "(ta meta)" }}
                  </span>
                  <span v-else-if="!h.verified && engine.metas.judge" class="inline-flex flex-wrap items-baseline gap-x-2 text-[0.8rem] text-courbe">
                    (amorce, à vérifier)
                    <button
                      type="button"
                      class="rounded px-1.5 text-foret underline underline-offset-2 hover:bg-foret/10 disabled:opacity-40"
                      :disabled="engine.busy"
                      :aria-label="`Juste : ${h.hint}`"
                      @click="judgeHint(lf.category, h.hint, 'right')"
                    >Juste</button>
                    <button
                      type="button"
                      class="rounded px-1.5 text-alerte underline underline-offset-2 hover:bg-alerte/10 disabled:opacity-40"
                      :disabled="engine.busy"
                      :aria-label="`Faux : ${h.hint}`"
                      @click="judgeHint(lf.category, h.hint, 'wrong')"
                    >Faux</button>
                  </span>
                  <span v-else-if="!h.verified" class="text-[0.8rem] text-courbe">(amorce, à vérifier)</span>
                </span>
              </li>
            </ul>
          </div>
        </div>
        <p v-else class="mt-4 border-l-2 border-foret/50 pl-3 text-[0.9rem] text-courbe">
          Aucune meta ne départage ces pays. Ajoute les tiennes dans ~/.config/geonesclick/mes-metas.toml.
        </p>

        <div v-if="similarByCountry.length" class="mt-6">
          <h3 class="text-[0.9rem] font-bold text-papier">Astuces Plonk It à chercher dans ta vue</h3>
          <p class="text-[0.8rem] text-courbe">Classées par ressemblance avec l'image : une piste à vérifier, pas une certitude.</p>
          <details v-for="(c, i) in similarByCountry" :key="c.code" :open="i === 0" class="mt-3 border-l-2 border-foret/40 pl-3">
            <summary class="cursor-pointer text-papier">
              <span aria-hidden="true" class="mr-1.5">{{ flag(c.code) }}</span>{{ countryName(c.code) }}
            </summary>
            <ul class="mt-2 space-y-3">
              <li v-for="tip in c.tips" :key="tip.text" class="text-[0.92rem] leading-snug text-papier/90">
                <span class="block text-[0.8rem] text-foret">{{ CATEGORY_LABELS[tip.category] ?? tip.category }}</span>
                <template v-for="(seg, k) in markdownSegments(tip.text)" :key="k"><strong v-if="seg.bold" class="text-papier">{{ seg.text }}</strong><template v-else>{{ seg.text }}</template></template>
              </li>
            </ul>
            <button
              type="button"
              class="mt-2 text-[0.85rem] text-courbe underline underline-offset-4 hover:text-papier"
              @click="openPlonkit(c.tips[0].url)"
            >
              Ouvrir le guide Plonk It ({{ countryName(c.code) }})
            </button>
          </details>
        </div>
      </template>
    </template>
  </section>
</template>
