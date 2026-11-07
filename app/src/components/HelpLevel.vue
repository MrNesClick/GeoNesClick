<script setup lang="ts">
// Sélecteur du niveau d'aide, toujours visible : change ce qui s'affiche tout de suite, et l'enregistre.
import { engine, setHelpLevel } from "../engine";

const LEVELS = [
  { value: 1, label: "Regarder", hint: "Où regarder, sans nommer de pays" },
  { value: 2, label: "Indices", hint: "Plus ce que voit l'IA, dont le texte lu" },
  { value: 3, label: "Pays", hint: "Plus les pays probables, leurs indices et les astuces Plonk It" },
  { value: 4, label: "Réponse", hint: "Plus la synthèse : pays, région si un texte la nomme, et la preuve" },
];
</script>

<template>
  <fieldset class="mt-3">
    <legend class="sr-only">Niveau d'aide</legend>
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
