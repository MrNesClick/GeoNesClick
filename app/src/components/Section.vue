<script setup lang="ts">
// Collapsible coach section: a one-line header (title + summary readable even when collapsed) and its content.
// The open/collapsed state of each section is remembered in this browser (personal convenience).
import { onBeforeUnmount, ref, watch } from "vue";

const props = withDefaults(
  defineProps<{ id: string; title: string; summary?: string; open?: boolean; tone?: "foret" | "lac" | "papier"; memory?: string }>(),
  { summary: "", open: true, tone: "foret", memory: "" },
);

const KEY = "geonesclick.sections";
// The name its state is remembered under: the id, unless one section is remembered apart in another layout.
const remembered = props.memory || props.id;
function saved(): Record<string, boolean> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}");
  } catch {
    return {};
  }
}
const isOpen = ref<boolean>(saved()[remembered] ?? props.open);
function toggle() {
  isOpen.value = !isOpen.value;
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...saved(), [remembered]: isOpen.value }));
  } catch {
    /* storage unavailable: the state will simply not be remembered */
  }
}
// The summary changes afterwards (AI answer, translation…): the header lights up briefly.
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
  <section :aria-labelledby="`${id}-title`" class="border-b border-courbe-fonce/70 pb-2">
    <h2 :id="`${id}-title`">
      <button
        type="button"
        class="flex w-full items-baseline gap-2.5 rounded px-1 py-2 text-left transition-colors duration-700 hover:text-papier focus-visible:outline-2 focus-visible:outline-lac motion-reduce:transition-none"
        :class="flash ? 'bg-lac/15' : ''"
        :aria-expanded="isOpen"
        :aria-controls="`${id}-content`"
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
    <div v-show="isOpen" :id="`${id}-content`" class="mb-2 ml-1.5 border-l-2 pl-4" :class="BORDER[tone]">
      <slot />
    </div>
  </section>
</template>
