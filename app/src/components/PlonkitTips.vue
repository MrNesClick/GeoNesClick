<script setup lang="ts">
// Plonk It tips for the candidate countries, ranked by similarity to the image (a lead, not a proof),
// translated on demand. Countries ruled out by proof that was read: no tips.
import { computed, reactive } from "vue";
import type { Analysis, SimilarTip } from "../engine";
import { categoryLabel, countryName, flag, markdownSegments, openPlonkit, tipsByCountry } from "../engine";
import { t } from "../i18n";

const props = defineProps<{ analysis: Analysis }>();

// Tips for which the player asked for the original text (English) rather than the translation.
const showOriginal = reactive(new Set<string>());
const tipText = (tip: SimilarTip) => (showOriginal.has(tip.id) || !tip.translated ? tip.text : tip.translated);
const toggleOriginal = (id: string) => (showOriginal.has(id) ? showOriginal.delete(id) : showOriginal.add(id));
const byCountry = computed(() => tipsByCountry(props.analysis));
const translation = computed(() => props.analysis.translation);
</script>

<template>
  <p class="text-[0.8rem] text-courbe">{{ t("tips.ranked") }}</p>
  <p v-if="translation && translation !== 'pending' && translation !== 'done'" class="text-[0.8rem] text-alerte">
    {{ translation[0].toUpperCase() + translation.slice(1) }}.
  </p>
  <div v-for="c in byCountry" :key="c.code" class="mt-3">
    <h3 class="text-papier"><span aria-hidden="true" class="mr-1.5">{{ flag(c.code) }}</span>{{ countryName(c.code) }}</h3>
    <ul class="mt-2 space-y-3">
      <li v-for="tip in c.tips" :key="tip.id" class="text-[0.92rem] leading-snug text-papier/90">
        <span class="block text-[0.8rem] text-foret">{{ categoryLabel(tip.category) }}</span>
        <template v-for="(seg, k) in markdownSegments(tipText(tip))" :key="k"><strong v-if="seg.bold" class="text-papier">{{ seg.text }}</strong><template v-else>{{ seg.text }}</template></template>
        <span v-if="tip.translated" class="block">
          <button type="button" class="text-[0.8rem] text-courbe underline underline-offset-2 hover:text-papier" @click="toggleOriginal(tip.id)">
            {{ t(showOriginal.has(tip.id) ? "tips.show_translation" : "tips.show_original") }}
          </button>
        </span>
        <span v-else-if="translation === 'pending'" class="block text-[0.8rem] text-courbe">{{ t("tips.translating") }}</span>
      </li>
    </ul>
    <button
      type="button"
      class="mt-2 text-[0.85rem] text-courbe underline underline-offset-4 hover:text-papier"
      @click="openPlonkit(c.tips[0].url)"
    >
      {{ t("tips.open_guide", { country: countryName(c.code) }) }}
    </button>
  </div>
</template>
