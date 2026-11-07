<script setup lang="ts">
// Niveau 2 : fiche d'indices du modèle de vision distant, masquée tant que tu ne la révèles pas.
import { computed } from "vue";
import type { Analysis, Fiche } from "../engine";
import { fr } from "../engine";

const props = defineProps<{ vision: Analysis["vision"]; revealed: boolean }>();
const emit = defineEmits<{ reveal: [] }>();

const LABELS: Record<string, string> = {
  sens_circulation: "Circulation",
  marquage_routier: "Marquage au sol",
  poteaux: "Poteaux",
  bornes_et_glissieres: "Bornes et glissières",
  panneaux_et_texte: "Panneaux et texte",
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
  <section aria-labelledby="n2-titre" class="text-lac">
    <header class="flex items-baseline justify-between gap-3">
      <h2 id="n2-titre" class="flex items-center gap-2 font-bold text-papier">
        <span class="grid size-6 place-items-center rounded-full border border-lac text-[0.8rem] text-lac" aria-label="Niveau">2</span>
        Ce que voit l'IA
      </h2>
      <span v-if="vision.status === 'done'" class="text-[0.8rem] text-courbe">{{ fr(vision.seconds) }} s</span>
    </header>

    <p v-if="vision.status === 'off'" class="mt-3 text-courbe">
      Le modèle de vision est désactivé dans la configuration.
    </p>

    <p v-else-if="vision.status === 'pending'" class="mt-3 flex items-center gap-2 text-courbe">
      <span class="inline-block size-2 animate-pulse rounded-full bg-lac motion-reduce:animate-none" aria-hidden="true" />
      Le modèle observe la vue…
    </p>

    <div v-else-if="vision.status === 'error'" class="mt-3 border-l-2 border-alerte pl-3 text-[0.9rem]" role="alert">
      <p class="text-papier">Le modèle de vision n'a pas répondu.</p>
      <p class="mt-1 break-words text-courbe">{{ vision.error }}</p>
    </div>

    <template v-else>
      <button
        v-if="!revealed"
        type="button"
        class="mt-3 w-full rounded-md border border-lac/40 px-4 py-3 text-left text-papier hover:border-lac hover:bg-lac/10"
        @click="emit('reveal')"
      >
        Révéler les observations
        <span class="block text-[0.85rem] text-courbe">Cherche d'abord par toi-même avec le niveau 1.</span>
      </button>

      <div v-else class="mt-3 space-y-3">
        <dl class="space-y-3">
          <div v-for="row in rows.seen" :key="row.label" class="border-l-2 border-lac/40 pl-3">
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
  </section>
</template>
