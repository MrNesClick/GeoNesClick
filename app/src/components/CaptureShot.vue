<script setup lang="ts">
// The analysed capture and its notes (crop guessed, plain image, same as before).
import type { Analysis } from "../engine";
import { t } from "../i18n";
import * as sum from "../summaries";

defineProps<{ analysis: Analysis }>();
</script>

<template>
  <img :src="analysis.thumbnail" :alt="t('app.capture_alt')" class="w-full rounded-md border border-courbe-fonce" />
  <p v-if="analysis.guessedCrop" class="mt-1 text-[0.85rem] text-courbe">{{ t("app.crop_guessed") }}</p>
  <p v-for="w in analysis.warnings" :key="w" class="mt-1 text-[0.85rem] text-alerte">{{ t(sum.WARNING_TEXT[w]) }}</p>
</template>
