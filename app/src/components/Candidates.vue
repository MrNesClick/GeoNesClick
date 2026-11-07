<script setup lang="ts">
// Niveau 1 : pays candidats calculés en local par StreetCLIP.
import { computed } from "vue";
import type { CountryScore } from "../engine";

const props = defineProps<{ scores: CountryScore[] | null; ms: number | null }>();

const regionNames = new Intl.DisplayNames(["fr"], { type: "region" });
const frName = (s: CountryScore) => regionNames.of(s.code) ?? s.name;
const flag = (code: string) =>
  String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));
const pct = (p: number) => `${Math.round(p * 100)} %`;

const leader = computed(() => props.scores?.[0] ?? null);
const others = computed(() => props.scores?.slice(1) ?? []);
// Échelle réelle de 0 à 100 % sur un rail : la longueur se lit comme le pourcentage affiché.
const width = (p: number) => `${Math.max(1.5, p * 100)}%`;
</script>

<template>
  <section aria-labelledby="n1-titre" class="text-foret">
    <header class="flex items-baseline justify-between gap-3">
      <h2 id="n1-titre" class="flex items-center gap-2 font-bold text-papier">
        <span class="grid size-6 place-items-center rounded-full border border-foret text-[0.8rem] text-foret" aria-label="Niveau">1</span>
        Pays probables
      </h2>
      <span v-if="ms !== null" class="text-[0.8rem] text-courbe">calcul local, {{ ms }} ms</span>
    </header>

    <p v-if="!scores" class="mt-3 text-courbe">Analyse de la vue en cours…</p>

    <template v-else-if="leader">
      <div class="mt-3">
        <p class="atlas text-[2rem] leading-tight font-semibold text-papier">
          <span aria-hidden="true" class="mr-2 not-italic">{{ flag(leader.code) }}</span>{{ frName(leader) }}
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
            <span aria-hidden="true" class="mr-1.5 not-italic">{{ flag(s.code) }}</span>{{ frName(s) }}
          </span>
          <div class="h-1 rounded-full bg-courbe-fonce" aria-hidden="true">
            <div class="jauge h-full rounded-full bg-foret/70" :style="{ width: width(s.probability) }" />
          </div>
          <span class="text-right tabular-nums text-courbe">{{ pct(s.probability) }}</span>
        </li>
      </ol>

      <p class="mt-4 border-l-2 border-foret/50 pl-3 text-[0.9rem] text-courbe">
        Les indices pour départager ces pays (poteaux, bornes, plaques…) arriveront avec la base de metas.
      </p>
    </template>
  </section>
</template>
