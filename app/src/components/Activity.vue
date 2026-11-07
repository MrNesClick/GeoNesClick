<script setup lang="ts">
// Ce qui tourne encore en arrière-plan pour la capture affichée, avec le temps écoulé.
// Rien n'est affiché quand tout est terminé.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { engine, fr } from "../engine";

const now = ref(Date.now());
let ticker: ReturnType<typeof setInterval> | undefined;

const tasks = computed(() => {
  const a = engine.current;
  if (!a) return [];
  const out: string[] = [];
  if (!a.scores) out.push("Analyse rapide en cours");
  if (a.vision.status === "pending") out.push("Analyse approfondie en cours");
  if (a.translation === "pending") out.push("Traduction des astuces");
  return out;
});
const elapsed = computed(() => (engine.current ? fr((now.value - engine.current.receivedAt) / 1000) : "0"));

watch(
  () => tasks.value.length > 0,
  (active) => {
    clearInterval(ticker);
    if (active) ticker = setInterval(() => (now.value = Date.now()), 250);
  },
  { immediate: true },
);
onBeforeUnmount(() => clearInterval(ticker));
</script>

<template>
  <p v-if="tasks.length" class="mt-2 flex items-center gap-2 text-[0.85rem] text-lac" role="status" aria-live="polite">
    <span class="inline-block size-2 shrink-0 animate-pulse rounded-full bg-lac motion-reduce:animate-none" aria-hidden="true" />
    <span class="min-w-0 flex-1 truncate">{{ tasks.join(" · ") }}…</span>
    <span class="shrink-0 tabular-nums text-courbe">{{ elapsed }} s</span>
  </p>
</template>
