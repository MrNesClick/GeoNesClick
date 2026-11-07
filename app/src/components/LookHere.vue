<script setup lang="ts">
// Niveaux d'aide 1 et 2 : où regarder pour départager les pays probables, sans en nommer aucun.
import type { LookFor } from "../engine";

defineProps<{ lookfor: LookFor[] | null }>();
</script>

<template>
  <p v-if="!lookfor" class="text-courbe">Analyse de la vue en cours…</p>
  <ol v-else-if="lookfor.length" class="space-y-2.5">
    <li v-for="lf in lookfor" :key="lf.category">
      <span class="text-papier">{{ lf.label }}</span>
      <span v-for="look in lf.looks" :key="look" class="block text-[0.9rem] text-foret">Regarde {{ look }}.</span>
    </li>
  </ol>
  <p v-else class="text-courbe">Aucune meta ne départage les pays probables de cette vue.</p>
</template>
