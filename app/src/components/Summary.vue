<script setup lang="ts">
// Niveau d'aide 4 : la synthèse en tête. Une preuve explicite lue par l'IA (texte, domaine, drapeau,
// plaque) l'emporte ; sinon, le pays le plus probable d'après l'allure de la vue (StreetCLIP), présenté
// comme tel.
import { computed } from "vue";
import type { Analysis } from "../engine";
import { countryName, flag, proofOf } from "../engine";

const props = defineProps<{ analysis: Analysis }>();

const pct = (p: number) => `${Math.round(p * 100)} %`;
const leader = computed(() => props.analysis.scores?.[0] ?? null);
const conclusion = computed(() => proofOf(props.analysis));
const clipOn = (code: string) => props.analysis.scores?.find((s) => s.code === code) ?? null;
</script>

<template>
  <div>
    <template v-if="conclusion">
      <p class="atlas mt-1 text-[1.9rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(conclusion.country) }}</span>{{ countryName(conclusion.country) }}
      </p>
      <p v-if="conclusion.region" class="text-[1.05rem] text-papier">{{ conclusion.region }}</p>
      <p v-if="conclusion.proof" class="mt-2 border-l-2 border-lac/60 pl-3 text-[0.92rem] text-papier/90">
        <span class="text-lac">Preuve lue par l'IA :</span> {{ conclusion.proof }}
      </p>
      <p class="mt-2 text-[0.85rem] text-courbe">
        <template v-if="clipOn(conclusion.country)">
          StreetCLIP le voyait aussi ({{ pct(clipOn(conclusion.country)!.probability) }}).
        </template>
        <template v-else-if="leader">
          StreetCLIP penchait pour {{ countryName(leader.code) }} ({{ pct(leader.probability) }}) : la preuve lue l'emporte.
        </template>
        <template v-if="conclusion.certainty"> Certitude : {{ conclusion.certainty }}.</template>
      </p>
    </template>

    <template v-else-if="leader">
      <p class="atlas mt-1 text-[1.9rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(leader.code) }}</span>{{ countryName(leader.code) }}
        <span class="text-[1.1rem] not-italic text-courbe">{{ pct(leader.probability) }}</span>
      </p>
      <p class="mt-1 text-[0.9rem] text-courbe">
        <template v-if="analysis.vision.status === 'pending'">
          D'après l'allure de la vue (StreetCLIP). Analyse approfondie en cours : si elle trouve une preuve
          écrite, elle s'affichera ici.
        </template>
        <template v-else>
          D'après l'allure de la vue (StreetCLIP) : aucune preuve écrite n'a été trouvée dans la vue.
        </template>
      </p>
    </template>

    <p v-else class="mt-1 text-courbe">Analyse de la vue en cours…</p>
  </div>
</template>
