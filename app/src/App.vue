<script setup lang="ts">
import { computed, ref } from "vue";
import Activity from "./components/Activity.vue";
import Countries from "./components/Countries.vue";
import HelpLevel from "./components/HelpLevel.vue";
import LabelForm from "./components/LabelForm.vue";
import LookHere from "./components/LookHere.vue";
import MetaHints from "./components/MetaHints.vue";
import Observations from "./components/Observations.vue";
import PlonkitTips from "./components/PlonkitTips.vue";
import Section from "./components/Section.vue";
import SettingsPanel from "./components/SettingsPanel.vue";
import Summary from "./components/Summary.vue";
import { engine, requestCapture, reselectWindow, restartSharing, tipsByCountry } from "./engine";
import * as sum from "./summaries";

const status = computed(() => {
  if (!engine.connected) return { tone: "bg-courbe", text: "Démarrage du moteur…" };
  if (engine.capture.starting) return { tone: "bg-courbe", text: "Choisis la fenêtre du jeu à partager…" };
  if (!engine.capture.alive) return { tone: "bg-alerte", text: engine.capture.message };
  if (!engine.streetclip.ready) return { tone: "bg-courbe", text: "Chargement du modèle local…" };
  return { tone: "bg-foret", text: "Prêt. Capture avec Super+Maj+G." };
});
const showSettings = ref(false);
const level = computed(() => engine.helpLevel);
</script>

<template>
  <div class="mx-auto flex min-h-screen max-w-xl flex-col px-4 py-4">
    <header class="flex items-center gap-3 border-b border-courbe-fonce pb-3">
      <span class="size-2.5 shrink-0 rounded-full" :class="status.tone" aria-hidden="true" />
      <p class="min-w-0 flex-1 truncate text-[0.9rem] text-courbe" role="status">{{ status.text }}</p>
      <button
        v-if="engine.connected && !engine.capture.alive && !engine.capture.starting"
        type="button"
        class="shrink-0 rounded-md border border-alerte/60 px-3 py-1.5 text-[0.9rem] text-papier hover:bg-alerte/10 disabled:opacity-50"
        :disabled="engine.busy"
        @click="restartSharing"
      >
        Relancer le partage
      </button>
      <button
        v-else
        type="button"
        class="shrink-0 rounded-md bg-papier px-3 py-1.5 text-[0.9rem] font-bold text-encre hover:bg-white disabled:opacity-40"
        :disabled="!engine.connected || !engine.capture.alive || engine.busy"
        @click="requestCapture"
      >
        Capturer
      </button>
    </header>

    <HelpLevel v-if="!showSettings" />
    <Activity v-if="!showSettings" />

    <p v-if="engine.error" class="mt-3 border-l-2 border-alerte pl-3 text-[0.9rem] text-papier" role="alert">
      {{ engine.error }}
    </p>

    <main v-if="showSettings" class="flex-1">
      <SettingsPanel @close="showSettings = false" />
    </main>

    <main v-else-if="engine.current" class="flex-1">
      <Transition name="arrivee" appear mode="out-in">
        <div :key="engine.current.id" class="pt-2">
          <!-- Sections dans l'ordre d'utilité ; le résumé de chacune reste lisible quand elle est repliée. -->
          <Section v-if="level >= 4" id="reponse" title="Réponse" tone="papier" :summary="sum.answer(engine.current)">
            <Summary :analysis="engine.current" />
          </Section>

          <Section id="capture" title="Capture" :open="false" tone="papier" :summary="sum.capture(engine.current)">
            <img :src="engine.current.thumbnail" alt="Vue analysée" class="w-full rounded-md border border-courbe-fonce" />
          </Section>

          <Section v-if="level < 3" id="regarder" title="Où regarder" :summary="sum.metas(engine.current)">
            <LookHere :lookfor="engine.current.lookfor" />
          </Section>

          <template v-else>
            <Section id="pays" title="Pays" :summary="sum.countries(engine.current)">
              <Countries :analysis="engine.current" />
            </Section>
            <Section id="departage" title="Ce qui les départage" :summary="sum.metas(engine.current)">
              <MetaHints :lookfor="engine.current.lookfor" />
            </Section>
            <Section
              v-if="tipsByCountry(engine.current).length"
              id="astuces"
              title="Astuces Plonk It"
              :open="false"
              :summary="sum.tips(engine.current)"
            >
              <PlonkitTips :analysis="engine.current" />
            </Section>
          </template>

          <Section v-if="level >= 2" id="ia" title="Ce que voit l'IA" tone="lac" :open="level === 2" :summary="sum.vision(engine.current)">
            <Observations :vision="engine.current.vision" />
          </Section>

          <Section v-if="engine.dataset.enabled" id="manche" title="Après la manche" :open="false" :summary="sum.round(engine.current)">
            <LabelForm :analysis="engine.current" :countries="engine.countries" :progress="engine.progress" />
          </Section>
        </div>
      </Transition>
    </main>

    <main v-else class="flex flex-1 flex-col justify-center py-10">
      <p class="atlas text-[1.6rem] leading-snug text-papier">Une vue, quelques indices.</p>
      <p class="mt-3 max-w-[34ch] text-courbe">
        Pendant une manche, appuie sur <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">Super</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">Maj</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">G</kbd>
        : le coach affiche tout seul l'aide du niveau choisi ci-dessus, de « Regarder » (où chercher, sans
        rien dévoiler) à « Réponse » (le pays et la preuve).
      </p>
    </main>

    <footer class="mt-6 flex items-center justify-between gap-3 border-t border-courbe-fonce pt-3 text-[0.85rem] text-courbe">
      <button
        type="button"
        class="rounded-md px-2 py-1 text-papier underline decoration-courbe underline-offset-4 hover:decoration-papier"
        @click="showSettings = !showSettings"
      >
        {{ showSettings ? "Retour au coach" : "Réglages" }}
      </button>
      <button
        title="Autre navigateur, écran ou résolution"
        type="button"
        class="shrink-0 rounded-md px-2 py-1 text-papier underline decoration-courbe underline-offset-4 hover:decoration-papier disabled:opacity-50"
        :disabled="!engine.connected || engine.busy || engine.capture.starting"
        @click="reselectWindow"
      >
        Changer de fenêtre
      </button>
    </footer>
  </div>
</template>
