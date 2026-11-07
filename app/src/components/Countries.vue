<script setup lang="ts">
// Pays probables (StreetCLIP, en local). Une preuve lue avec certitude forte met son pays en tête,
// « certain », et écarte les autres ; le pourcentage de StreetCLIP reste affiché pour comparer.
// Sans preuve, le premier n'est mis en avant que s'il se détache (même règle que la carte Réponse).
import { computed } from "vue";
import type { Analysis } from "../engine";
import { certainProof, clearLeader, countryName, flag, proofLabel, proofOf } from "../engine";

const props = defineProps<{ analysis: Analysis }>();

const pct = (p: number) => `${Math.round(p * 100)} %`;
// Échelle réelle de 0 à 100 % sur un rail : la longueur se lit comme le pourcentage affiché.
const width = (p: number) => `${Math.max(1.5, p * 100)}%`;
const scores = computed(() => props.analysis.scores ?? []);
const first = computed(() => scores.value[0] ?? null);
const leader = computed(() => clearLeader(props.analysis));
const proof = computed(() => proofOf(props.analysis));
const certain = computed(() => certainProof(props.analysis));
const clipOf = (code: string) => scores.value.find((s) => s.code === code) ?? null;
// Lu par l'IA mais pas encore confirmé : ce pays passe en tête, « très probable », sans écarter les autres.
const likely = computed(() => (!certain.value && proof.value ? proof.value : null));
const others = computed(() => {
  const top = certain.value?.country ?? likely.value?.country;
  if (top) return scores.value.filter((s) => s.code !== top);
  return leader.value ? scores.value.slice(1) : scores.value; // hésitation : tous au même rang
});
</script>

<template>
  <p v-if="!first" class="text-courbe">Analyse de la vue en cours…</p>

  <template v-else>
    <div v-if="certain">
      <p class="atlas text-[1.8rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(certain.country) }}</span>{{ countryName(certain.country) }}
      </p>
      <div class="mt-2 flex items-center gap-3">
        <div class="h-1.5 flex-1 rounded-full bg-lac" aria-hidden="true" />
        <span class="shrink-0 text-papier">Certain</span>
      </div>
      <p class="mt-1.5 text-[0.85rem] text-courbe">
        Mis à jour après la lecture de l'IA : {{ certain.proof || "texte de la vue" }}.
        <template v-if="clipOf(certain.country)">D'après la seule allure de la vue, StreetCLIP donnait {{ pct(clipOf(certain.country)!.probability) }}.</template>
        <template v-else>StreetCLIP ne le comptait pas parmi ses pays probables.</template>
      </p>
    </div>

    <div v-else-if="likely">
      <p class="atlas text-[1.8rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(likely.country) }}</span>{{ countryName(likely.country) }}
      </p>
      <p class="mt-1 text-[0.9rem] text-papier/80">{{ proofLabel(likely) }}.</p>
      <p class="mt-1 text-[0.85rem] text-courbe">
        {{ likely.proof || "Texte de la vue" }}.
        <template v-if="clipOf(likely.country)">StreetCLIP : {{ pct(clipOf(likely.country)!.probability) }}.</template>
        <template v-else>StreetCLIP ne le comptait pas parmi ses pays probables.</template>
      </p>
    </div>

    <div v-else-if="leader">
      <p class="atlas text-[1.8rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(leader.code) }}</span>{{ countryName(leader.code) }}
      </p>
      <div class="mt-2 flex items-center gap-3">
        <div class="h-1.5 flex-1 rounded-full bg-courbe-fonce" aria-hidden="true">
          <div class="jauge h-full rounded-full bg-foret" :style="{ width: width(leader.probability) }" />
        </div>
        <span class="w-12 shrink-0 text-right tabular-nums text-papier">{{ pct(leader.probability) }}</span>
      </div>
      <p v-if="proof" class="mt-1.5 text-[0.85rem] text-lac">
        Preuve lue (certitude {{ proof.certainty || "non précisée" }}) : {{ countryName(proof.country) }}, {{ proof.proof }}.
      </p>
    </div>

    <div v-else>
      <p class="text-papier"><span class="font-bold">Hésitation</span> <span class="text-courbe">: aucun pays ne se détache.</span></p>
      <p v-if="proof" class="mt-1.5 text-[0.85rem] text-lac">
        Preuve lue (certitude {{ proof.certainty || "non précisée" }}) : {{ countryName(proof.country) }}, {{ proof.proof }}.
      </p>
    </div>

    <ol v-if="others.length" class="space-y-2" :class="leader || certain || likely ? 'mt-4' : 'mt-2'"
        :aria-label="certain ? 'Pays écartés par la preuve' : leader || likely ? 'Autres candidats' : 'Pays candidats'">
      <li
        v-for="s in others"
        :key="s.code"
        class="grid grid-cols-[8.5rem_1fr_3.5rem] items-center gap-3"
        :class="certain ? 'opacity-50' : ''"
      >
        <span class="atlas truncate text-papier/90" :class="certain ? 'line-through decoration-courbe' : ''">
          <span aria-hidden="true" class="mr-1.5 not-italic">{{ flag(s.code) }}</span>{{ countryName(s.code) }}
        </span>
        <div class="h-1 rounded-full bg-courbe-fonce" aria-hidden="true">
          <div v-if="!certain" class="jauge h-full rounded-full bg-foret/70" :style="{ width: width(s.probability) }" />
        </div>
        <span class="text-right tabular-nums text-courbe">{{ certain ? "écarté" : pct(s.probability) }}</span>
      </li>
    </ol>
  </template>
</template>
