<script setup lang="ts">
// Astuces Plonk It des pays candidats, classées par ressemblance avec l'image (une piste, pas une preuve),
// traduites à la demande. Pays écartés par une preuve lue : pas d'astuces.
import { computed, reactive } from "vue";
import type { Analysis, SimilarTip } from "../engine";
import { CATEGORY_LABELS, countryName, flag, markdownSegments, openPlonkit, tipsByCountry } from "../engine";

const props = defineProps<{ analysis: Analysis }>();

// Astuces dont le joueur a demandé le texte original (anglais) plutôt que la traduction.
const showOriginal = reactive(new Set<string>());
const tipText = (tip: SimilarTip) => (showOriginal.has(tip.id) || !tip.translated ? tip.text : tip.translated);
const toggleOriginal = (id: string) => (showOriginal.has(id) ? showOriginal.delete(id) : showOriginal.add(id));
const byCountry = computed(() => tipsByCountry(props.analysis));
const translation = computed(() => props.analysis.translation);
</script>

<template>
  <p class="text-[0.8rem] text-courbe">Classées par ressemblance avec l'image : une piste à vérifier, pas une certitude.</p>
  <p v-if="translation && translation !== 'pending' && translation !== 'done'" class="text-[0.8rem] text-alerte">
    Astuces en anglais : {{ translation }}.
  </p>
  <div v-for="c in byCountry" :key="c.code" class="mt-3">
    <h3 class="text-papier"><span aria-hidden="true" class="mr-1.5">{{ flag(c.code) }}</span>{{ countryName(c.code) }}</h3>
    <ul class="mt-2 space-y-3">
      <li v-for="tip in c.tips" :key="tip.id" class="text-[0.92rem] leading-snug text-papier/90">
        <span class="block text-[0.8rem] text-foret">{{ CATEGORY_LABELS[tip.category] ?? tip.category }}</span>
        <template v-for="(seg, k) in markdownSegments(tipText(tip))" :key="k"><strong v-if="seg.bold" class="text-papier">{{ seg.text }}</strong><template v-else>{{ seg.text }}</template></template>
        <span v-if="tip.translated" class="block">
          <button type="button" class="text-[0.8rem] text-courbe underline underline-offset-2 hover:text-papier" @click="toggleOriginal(tip.id)">
            {{ showOriginal.has(tip.id) ? "Voir la traduction" : "Voir l'original" }}
          </button>
        </span>
        <span v-else-if="translation === 'pending'" class="block text-[0.8rem] text-courbe">traduction en cours…</span>
      </li>
    </ul>
    <button
      type="button"
      class="mt-2 text-[0.85rem] text-courbe underline underline-offset-4 hover:text-papier"
      @click="openPlonkit(c.tips[0].url)"
    >
      Ouvrir le guide Plonk It ({{ countryName(c.code) }})
    </button>
  </div>
</template>
