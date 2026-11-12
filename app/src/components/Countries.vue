<script setup lang="ts">
// Likely countries (StreetCLIP, local). Proof read with strong certainty puts its country first,
// "certain", and rules out the others; StreetCLIP's percentage stays visible for comparison.
// Without proof, the first one is highlighted only if it stands out (same rule as the Answer card).
import { computed } from "vue";
import type { Analysis } from "../engine";
import { certainProof, clearLeader, countryName, excluded, flag, proofLabel, proofOf } from "../engine";
import { pct, t, valueLabel } from "../i18n";

const props = defineProps<{ analysis: Analysis }>();

// Real scale from 0 to 100 % on a rail: the length reads like the displayed percentage.
const width = (p: number) => `${Math.max(1.5, p * 100)}%`;
const scores = computed(() => props.analysis.scores ?? []);
const first = computed(() => scores.value[0] ?? null);
const leader = computed(() => clearLeader(props.analysis));
const proof = computed(() => proofOf(props.analysis));
const certain = computed(() => certainProof(props.analysis));
const clipOf = (code: string) => scores.value.find((s) => s.code === code) ?? null;
// Read by the AI but not confirmed yet: this country goes first, "very likely", without ruling out the others.
const likely = computed(() => (!certain.value && proof.value ? proof.value : null));
const others = computed(() => {
  const top = certain.value?.country ?? likely.value?.country;
  if (top) return scores.value.filter((s) => s.code !== top);
  return leader.value ? scores.value.filter((s) => s.code !== leader.value!.code) : scores.value; // tie: same rank
});
// Ruled out: by certain proof, or by the alphabet of your marks ("Cyrillic" excludes France).
const out = (code: string) => !!certain.value || excluded(props.analysis, code);
</script>

<template>
  <p v-if="!first" class="text-courbe">{{ t("look.analysing") }}</p>

  <template v-else>
    <div v-if="certain">
      <p class="atlas text-[1.8rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(certain.country) }}</span>{{ countryName(certain.country) }}
      </p>
      <div class="mt-2 flex items-center gap-3">
        <div class="h-1.5 flex-1 rounded-full bg-lac" aria-hidden="true" />
        <span class="shrink-0 text-papier">{{ t("countries.certain") }}</span>
      </div>
      <p class="mt-1.5 text-[0.85rem] text-courbe">
        {{ t("summary.label_colon", { label: t(certain.source === "marks" ? "countries.proven_by_marks" : "countries.updated_after_ai") }) }} {{ certain.proof || t("countries.view_text") }}.
        <template v-if="clipOf(certain.country)">{{ t("countries.clip_gave", { pct: pct(clipOf(certain.country)!.probability) }) }}</template>
        <template v-else>{{ t("countries.clip_absent") }}</template>
      </p>
    </div>

    <div v-else-if="likely">
      <p class="atlas text-[1.8rem] leading-tight font-semibold text-papier">
        <span aria-hidden="true" class="mr-2 not-italic">{{ flag(likely.country) }}</span>{{ countryName(likely.country) }}
      </p>
      <p class="mt-1 text-[0.9rem] text-papier/80">{{ proofLabel(likely) }}.</p>
      <p class="mt-1 text-[0.85rem] text-courbe">
        {{ likely.proof || t("countries.view_text_cap") }}.
        <template v-if="clipOf(likely.country)">{{ t("countries.clip_pct", { pct: pct(clipOf(likely.country)!.probability) }) }}</template>
        <template v-else>{{ t("countries.clip_absent") }}</template>
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
        {{ t("countries.proof_read", { certainty: proof.certainty ? valueLabel("value.certitude", proof.certainty) : t("countries.unspecified"), country: countryName(proof.country), proof: proof.proof }) }}
      </p>
    </div>

    <div v-else>
      <p class="text-papier"><span class="font-bold">{{ t("summary.hesitation") }}</span><span class="text-courbe">{{ t("countries.no_standout") }}</span></p>
      <p v-if="proof" class="mt-1.5 text-[0.85rem] text-lac">
        {{ t("countries.proof_read", { certainty: proof.certainty ? valueLabel("value.certitude", proof.certainty) : t("countries.unspecified"), country: countryName(proof.country), proof: proof.proof }) }}
      </p>
    </div>

    <ol v-if="others.length" class="space-y-2" :class="leader || certain || likely ? 'mt-4' : 'mt-2'"
        :aria-label="t(certain ? 'countries.ruled_out_aria' : leader || likely ? 'countries.others_aria' : 'countries.candidates_aria')">
      <li
        v-for="s in others"
        :key="s.code"
        class="grid grid-cols-[8.5rem_1fr_3.5rem] items-center gap-3"
        :class="out(s.code) ? 'opacity-50' : ''"
      >
        <span class="atlas truncate text-papier/90" :class="out(s.code) ? 'line-through decoration-courbe' : ''">
          <span aria-hidden="true" class="mr-1.5 not-italic">{{ flag(s.code) }}</span>{{ countryName(s.code) }}
        </span>
        <div class="h-1 rounded-full bg-courbe-fonce" aria-hidden="true">
          <div v-if="!out(s.code)" class="jauge h-full rounded-full bg-foret/70" :style="{ width: width(s.probability) }" />
        </div>
        <span class="text-right tabular-nums text-courbe" :title="!certain && out(s.code) ? t('countries.ruled_out_by_alphabet') : ''">
          {{ out(s.code) ? t("countries.ruled_out") : pct(s.probability) }}
        </span>
      </li>
    </ol>

  </template>
</template>
