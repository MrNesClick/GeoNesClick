<script setup lang="ts">
// Help level selector, always visible: changes what is displayed right away, and saves it.
import { computed } from "vue";
import { engine, setHelpLevel } from "../engine";
import { t } from "../i18n";

const LEVELS = computed(() => ([1, 2, 3, 4] as const).map((value) => (
  { value, label: t(`level.${value}`), hint: t(`level.${value}.hint`) })));
</script>

<template>
  <fieldset class="mt-3">
    <legend class="sr-only">{{ t("level.legend") }}</legend>
    <div class="grid grid-cols-4 gap-1 rounded-md border border-courbe-fonce p-1">
      <label
        v-for="lvl in LEVELS"
        :key="lvl.value"
        :title="lvl.hint"
        class="cursor-pointer rounded px-2 py-1.5 text-center text-[0.85rem] transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-lac motion-reduce:transition-none"
        :class="engine.helpLevel === lvl.value ? 'bg-papier font-bold text-encre' : 'text-courbe hover:text-papier'"
      >
        <input
          type="radio"
          name="niveau-aide"
          class="sr-only"
          :value="lvl.value"
          :checked="engine.helpLevel === lvl.value"
          @change="setHelpLevel(lvl.value)"
        />
        {{ lvl.label }}
      </label>
    </div>
  </fieldset>
</template>
