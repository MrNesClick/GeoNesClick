<script setup lang="ts">
// Niveau d'aide 4 : la synthèse en tête. La preuve tirée de tes marques par les règles locales l'emporte, puis
// celle lue par l'IA sur la vue entière (si l'alphabet de tes marques ne l'exclut pas) ; sinon, le pays le plus
// probable d'après l'allure de la vue (StreetCLIP), mais SEULEMENT s'il se détache. Sinon : « Hésitation ».
import { computed } from "vue";
import type { Analysis } from "../engine";
import { circled, clearLeader, contenders, countryName, flag, proofLabel, proofOf, rejectedVision, unreadableText } from "../engine";

const props = defineProps<{ analysis: Analysis }>();

const pct = (p: number) => `${Math.round(p * 100)} %`;
const first = computed(() => props.analysis.scores?.[0] ?? null);
const leader = computed(() => clearLeader(props.analysis));
const close = computed(() => contenders(props.analysis));
const conclusion = computed(() => proofOf(props.analysis));
const unreadable = computed(() => unreadableText(props.analysis));
const clipOn = (code: string) => props.analysis.scores?.find((s) => s.code === code) ?? null;
const verdict = computed(() => props.analysis.verdict);
const rejected = computed(() => rejectedVision(props.analysis));
</script>

<template>
  <div>
    <template v-if="conclusion">
      <p class="atlas mt-1 text-[1.9rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(conclusion.country) }}</span>{{ countryName(conclusion.country) }}
      </p>
      <p v-if="conclusion.region" class="text-[1.05rem] text-papier">{{ conclusion.region }}</p>
      <p class="text-[0.95rem]" :class="conclusion.confirmed ? 'text-lac' : 'text-papier/80'">
        {{ proofLabel(conclusion) }}
      </p>
      <p v-if="conclusion.proof" class="mt-2 border-l-2 border-lac/60 pl-3 text-[0.92rem] text-papier/90">
        <span class="text-lac">{{ conclusion.confirmed ? "Preuve" : conclusion.source === "marks" ? "Lu dans tes marques" : "Ce que l'IA a lu" }} :</span> {{ conclusion.proof }}
      </p>
      <p v-for="a in conclusion.source === 'marks' ? verdict?.against ?? [] : []" :key="a.n"
         class="mt-2 border-l-2 border-alerte/70 pl-3 text-[0.9rem] text-papier">
        {{ circled(a.n) }} désigne {{ flag(a.country) }} {{ countryName(a.country) }} (« {{ a.items.join(", ") }} ») : lecture
        douteuse ? Si elle est fausse, retire-la dans « Marques » et la réponse deviendra certaine.
      </p>
      <p class="mt-2 text-[0.85rem] text-courbe">
        <template v-if="clipOn(conclusion.country)">
          StreetCLIP le voyait aussi ({{ pct(clipOn(conclusion.country)!.probability) }}).
        </template>
        <template v-else-if="first">
          StreetCLIP penchait pour {{ countryName(first.code) }} ({{ pct(first.probability) }}) : la preuve lue l'emporte.
        </template>
        <template v-if="conclusion.source === 'vision'"> Vérifie le texte toi-même : le modèle se trompe parfois en le lisant.</template>
      </p>
    </template>

    <template v-else-if="leader">
      <p class="atlas mt-1 text-[1.9rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(leader.code) }}</span>{{ countryName(leader.code) }}
        <span class="text-[1.1rem] not-italic text-courbe">{{ pct(leader.probability) }}</span>
      </p>
      <p class="mt-1 text-[0.9rem] text-courbe">D'après l'allure de la vue (StreetCLIP), sans preuve écrite.</p>
    </template>

    <template v-else-if="first">
      <p class="atlas mt-1 text-[1.6rem] leading-tight font-semibold text-papier">Hésitation</p>
      <ul class="mt-1.5 flex flex-wrap gap-x-4 gap-y-1" aria-label="Pays entre lesquels StreetCLIP hésite">
        <li v-for="s in close" :key="s.code" class="text-papier">
          <span aria-hidden="true" class="mr-1">{{ flag(s.code) }}</span>{{ countryName(s.code) }}
          <span class="tabular-nums text-courbe">{{ pct(s.probability) }}</span>
        </li>
      </ul>
      <p class="mt-1.5 text-[0.9rem] text-courbe">
        L'allure de la vue ne suffit pas à trancher : aucun pays ne se détache.
      </p>
    </template>

    <p v-else class="mt-1 text-courbe">Analyse de la vue en cours…</p>

    <!-- Cohérence : ce que l'alphabet de tes marques écarte, y compris une lecture de l'IA sur la vue entière. -->
    <p v-if="verdict?.allowed" class="mt-2 text-[0.85rem] text-courbe">
      Alphabet de tes marques : {{ verdict.scripts.join(", ") }}. Seuls restent possibles
      {{ verdict.allowed.map(flag).join(" ") }}.
    </p>
    <p v-if="rejected" class="mt-1 text-[0.85rem] text-courbe">
      L'IA a cru lire sur la vue entière une preuve pour {{ countryName(rejected.country) }} (« {{ rejected.proof }} ») :
      écartée, l'alphabet de tes marques l'exclut.
    </p>
    <p v-if="verdict?.conflict" class="mt-1 text-[0.85rem] text-alerte">Tes marques se contredisent ({{ verdict.conflict }}).</p>

    <!-- Que faire maintenant, quand il n'y a pas de preuve -->
    <template v-if="first && !conclusion">
      <p v-if="analysis.vision.status === 'pending'" class="mt-2 text-[0.85rem] text-courbe">
        Analyse approfondie en cours : si elle lit une preuve écrite, elle s'affichera ici.
      </p>
      <p v-else-if="unreadable" class="mt-2 border-l-2 border-alerte/70 pl-3 text-[0.9rem] text-papier">
        Du texte est visible mais <strong>illisible</strong> à cette taille : zoome dessus dans le jeu, puis recapture.
        C'est souvent lui qui tranche.
      </p>
      <p v-else-if="!leader" class="mt-2 text-[0.85rem] text-courbe">
        Cherche du texte, une plaque ou un domaine ; sinon, « Ce qui les départage » dit quoi observer.
      </p>
    </template>
  </div>
</template>
