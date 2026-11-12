<script setup lang="ts">
// What the AI sees (remote vision model), shown from help level 2.
import { computed } from "vue";
import type { Analysis, Fiche } from "../engine";
import { t, valueLabel } from "../i18n";

const props = defineProps<{ vision: Analysis["vision"] }>();

// The text read first: it is the most decisive clue when there is one.
// Keys of the model's answer (internal, in French as in the prompt), in display order.
const FIELDS = ["panneaux_et_texte", "sens_circulation", "marquage_routier", "poteaux", "bornes_et_glissieres",
                "plaques_immatriculation", "architecture", "vegetation_et_sol", "relief", "camera_et_voiture_google",
                "autres_indices"] as const;

const asText = (v: unknown) => (Array.isArray(v) ? v.join(" ; ") : String(v ?? ""));
const isEmpty = (v: string) => /^(non visible|aucun|indéterminé)?\.?$/i.test(v.trim());

const rows = computed(() => {
  if (props.vision.status !== "done") return { seen: [], unseen: [] as string[] };
  const fiche: Fiche = props.vision.fiche;
  const seen: { label: string; value: string; proof?: string }[] = [];
  const unseen: string[] = [];
  for (const key of FIELDS) {
    const label = t(`vision.field.${key}`);
    const value = asText(fiche[key]);
    if (isEmpty(value)) unseen.push(label);
    else seen.push({ label, value, proof: key === "sens_circulation" ? asText(fiche.preuve_circulation) : undefined });
  }
  return { seen, unseen };
});
const confidence = computed(() => (props.vision.status === "done" ? valueLabel("value.confiance", asText(props.vision.fiche.confiance)) : ""));
</script>

<template>
  <div class="text-lac">

    <p v-if="vision.status === 'off'" class="text-courbe">
      {{ t("vision.off") }}
    </p>

    <p v-else-if="vision.status === 'pending'" class="flex items-center gap-2 text-courbe">
      <span class="inline-block size-2 animate-pulse rounded-full bg-lac motion-reduce:animate-none" aria-hidden="true" />
      {{ t("vision.pending") }}
    </p>

    <div v-else-if="vision.status === 'error'" class="text-[0.9rem]" role="alert">
      <p class="text-papier">{{ t("vision.no_answer") }}</p>
      <p class="mt-1 break-words text-courbe">{{ vision.error }}</p>
    </div>

    <template v-else>
      <div class="space-y-3">
        <dl class="space-y-3">
          <div v-for="row in rows.seen" :key="row.label">
            <dt class="text-[0.85rem] text-lac">{{ row.label }}</dt>
            <dd class="text-papier">{{ row.value }}</dd>
            <dd v-if="row.proof && !isEmpty(row.proof)" class="text-[0.85rem] text-courbe">{{ row.proof }}</dd>
          </div>
        </dl>
        <p v-if="rows.unseen.length" class="text-[0.85rem] text-courbe">
          {{ t("vision.not_visible", { fields: rows.unseen.join(", ").toLowerCase() }) }}
        </p>
        <p v-if="confidence" class="text-[0.85rem] text-courbe">
          {{ t("vision.confidence", { value: confidence, model: vision.status === "done" ? vision.model.split("/").pop() ?? "" : "" }) }}
        </p>
      </div>
    </template>
  </div>
</template>
