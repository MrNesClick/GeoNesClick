<script setup lang="ts">
// Ce que voit l'IA (modèle de vision distant), affiché dès le niveau d'aide 2.
import { computed } from "vue";
import type { Analysis, Fiche } from "../engine";

const props = defineProps<{ vision: Analysis["vision"] }>();

// Le texte lu d'abord : c'est l'indice le plus décisif quand il existe.
const LABELS: Record<string, string> = {
  panneaux_et_texte: "Texte lu et panneaux",
  sens_circulation: "Circulation",
  marquage_routier: "Marquage au sol",
  poteaux: "Poteaux",
  bornes_et_glissieres: "Bornes et glissières",
  plaques_immatriculation: "Plaques",
  architecture: "Architecture",
  vegetation_et_sol: "Végétation et sol",
  relief: "Relief",
  camera_et_voiture_google: "Caméra et voiture Google",
  autres_indices: "Autres indices",
};

const asText = (v: unknown) => (Array.isArray(v) ? v.join(" ; ") : String(v ?? ""));
const isEmpty = (v: string) => /^(non visible|aucun|indéterminé)?\.?$/i.test(v.trim());

const rows = computed(() => {
  if (props.vision.status !== "done") return { seen: [], unseen: [] as string[] };
  const fiche: Fiche = props.vision.fiche;
  const seen: { label: string; value: string; proof?: string }[] = [];
  const unseen: string[] = [];
  for (const [key, label] of Object.entries(LABELS)) {
    const value = asText(fiche[key]);
    if (isEmpty(value)) unseen.push(label);
    else seen.push({ label, value, proof: key === "sens_circulation" ? asText(fiche.preuve_circulation) : undefined });
  }
  return { seen, unseen };
});
const confidence = computed(() => (props.vision.status === "done" ? asText(props.vision.fiche.confiance) : ""));
</script>

<template>
  <div class="text-lac">

    <p v-if="vision.status === 'off'" class="text-courbe">
      Le modèle de vision est désactivé dans la configuration.
    </p>

    <p v-else-if="vision.status === 'pending'" class="flex items-center gap-2 text-courbe">
      <span class="inline-block size-2 animate-pulse rounded-full bg-lac motion-reduce:animate-none" aria-hidden="true" />
      Analyse approfondie en cours…
    </p>

    <div v-else-if="vision.status === 'error'" class="text-[0.9rem]" role="alert">
      <p class="text-papier">Le modèle de vision n'a pas répondu.</p>
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
          Non visible : {{ rows.unseen.join(", ").toLowerCase() }}.
        </p>
        <p v-if="confidence" class="text-[0.85rem] text-courbe">
          Confiance du modèle : {{ confidence }} ({{ vision.status === "done" ? vision.model.split("/").pop() : "" }})
        </p>
      </div>
    </template>
  </div>
</template>
