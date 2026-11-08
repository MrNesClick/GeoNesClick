<script setup lang="ts">
// What is still running in the background for the displayed capture, with the time elapsed since the start of the
// oldest running task (a marks reading counts from its launch, not from the capture).
// Nothing is shown once everything is done.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { engine, fr } from "../engine";

const now = ref(Date.now());
let ticker: ReturnType<typeof setInterval> | undefined;

const tasks = computed(() => {
  const a = engine.current;
  if (!a) return [];
  const out: { label: string; since: number }[] = [];
  if (!a.scores) out.push({ label: "Analyse rapide en cours", since: a.receivedAt });
  if (a.vision.status === "pending") out.push({ label: "Analyse approfondie en cours", since: a.receivedAt });
  if (a.translation === "pending") out.push({ label: "Traduction des astuces", since: a.receivedAt });
  const reading = a.marks.filter((m) => m.status === "pending");
  if (reading.length) {
    out.push({
      label: reading.length > 1 ? `Lecture de ${reading.length} marques` : "Lecture d'une marque",
      since: Math.min(...reading.map((m) => m.startedAt ?? Date.now())),
    });
  }
  return out;
});
const elapsed = computed(() =>
  tasks.value.length ? fr((now.value - Math.min(...tasks.value.map((t) => t.since))) / 1000) : "0");

watch(
  () => tasks.value.length > 0,
  (active) => {
    clearInterval(ticker);
    now.value = Date.now(); // otherwise the last value, frozen at the end of the previous task
    if (active) ticker = setInterval(() => (now.value = Date.now()), 250);
  },
  { immediate: true },
);
onBeforeUnmount(() => clearInterval(ticker));
</script>

<template>
  <p v-if="tasks.length" class="mt-2 flex items-center gap-2 text-[0.85rem] text-lac" role="status" aria-live="polite">
    <span class="inline-block size-2 shrink-0 animate-pulse rounded-full bg-lac motion-reduce:animate-none" aria-hidden="true" />
    <span class="min-w-0 flex-1 truncate">{{ tasks.map((t) => t.label).join(" · ") }}…</span>
    <span class="shrink-0 tabular-nums text-courbe">{{ elapsed }} s</span>
  </p>
</template>
