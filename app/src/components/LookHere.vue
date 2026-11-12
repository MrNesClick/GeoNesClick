<script setup lang="ts">
// Help levels 1 and 2: where to look to tell the likely countries apart, without naming any.
import type { LookFor } from "../engine";
import { t } from "../i18n";

defineProps<{ lookfor: LookFor[] | null }>();
</script>

<template>
  <p v-if="!lookfor" class="text-courbe">{{ t("look.analysing") }}</p>
  <ol v-else-if="lookfor.length" class="space-y-2.5">
    <li v-for="lf in lookfor" :key="lf.category">
      <span class="text-papier">{{ lf.label }}</span>
      <span v-for="look in lf.looks" :key="look" class="block text-[0.9rem] text-foret">{{ t("look.look_at", { what: look }) }}</span>
    </li>
  </ol>
  <p v-else class="text-courbe">{{ t("look.none") }}</p>
</template>
