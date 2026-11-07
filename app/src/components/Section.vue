<script setup lang="ts">
// Section repliable du coach : un en-tête d'une ligne (titre + résumé lisible même replié) et son contenu.
// L'état ouvert/replié de chaque section est mémorisé dans ce navigateur (confort personnel).
import { onBeforeUnmount, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{ id: string; title: string; summary?: string; open?: boolean; tone?: "foret" | "lac" | "papier" }>(),
  { summary: "", open: true, tone: "foret" },
);

const KEY = "ggc.sections";
function saved(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}");
  } catch {
    return {};
  }
}
const isOpen = ref<boolean>(saved()[props.id] ?? props.open);
function toggle() {
  isOpen.value = !isOpen.value;
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...saved(), [props.id]: isOpen.value }));
  } catch {
    /* stockage indisponible : l'état ne sera simplement pas mémorisé */
  }
}
// Le résumé change après coup (réponse de l'IA, traduction…) : l'en-tête s'illumine brièvement.
const flash = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => props.summary,
  (now, before) => {
    if (!before || now === before) return;
    flash.value = true;
    clearTimeout(timer);
    timer = setTimeout(() => (flash.value = false), 1600);
  },
);
onBeforeUnmount(() => clearTimeout(timer));
const BORDER = { foret: "border-foret/50", lac: "border-lac/50", papier: "border-papier/40" };
</script>

<template>
  <section :aria-labelledby="`${id}-titre`" class="border-b border-courbe-fonce/70 pb-2">
    <h2 :id="`${id}-titre`">
      <button
        type="button"
        class="flex w-full items-baseline gap-2.5 rounded px-1 py-2 text-left transition-colors duration-700 hover:text-papier focus-visible:outline-2 focus-visible:outline-lac motion-reduce:transition-none"
        :class="flash ? 'bg-lac/15' : ''"
        :aria-expanded="isOpen"
        :aria-controls="`${id}-contenu`"
        @click="toggle"
      >
        <span
          aria-hidden="true"
          class="inline-block w-3 shrink-0 text-courbe transition-transform motion-reduce:transition-none"
          :class="isOpen ? 'rotate-90' : ''"
        >▸</span>
        <span class="shrink-0 font-bold text-papier">{{ title }}</span>
        <span class="min-w-0 flex-1 truncate text-right text-[0.85rem] text-courbe">
          <slot name="summary">{{ summary }}</slot>
        </span>
      </button>
    </h2>
    <div v-show="isOpen" :id="`${id}-contenu`" class="mb-2 ml-1.5 border-l-2 pl-4" :class="BORDER[tone]">
      <slot />
    </div>
  </section>
</template>
