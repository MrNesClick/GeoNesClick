<script setup lang="ts">
import { computed, ref, watch } from "vue";
import Activity from "./components/Activity.vue";
import CoachMap from "./components/CoachMap.vue";
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
import { engine, requestCapture, restartSharing, tipsByCountry } from "./engine";
import * as sum from "./summaries";

const status = computed(() => {
  if (!engine.connected) return { tone: "bg-courbe", text: "Démarrage du moteur…" };
  if (engine.capture.starting) return { tone: "bg-courbe", text: "Choisis la fenêtre du jeu à partager…" };
  if (!engine.capture.alive) return { tone: "bg-alerte", text: engine.capture.message };
  if (!engine.streetclip.ready) return { tone: "bg-courbe", text: "Chargement du modèle local…" };
  return { tone: "bg-foret", text: "Prêt. Capture avec Super+Maj+G." };
});
// Vues de la fenêtre : le coach, la carte en grand (niveau 3 et plus), les réglages.
const view = ref<"coach" | "map" | "settings">("coach");
const showSettings = computed(() => view.value === "settings");
const level = computed(() => engine.helpLevel);
const mapAvailable = computed(() => engine.map.enabled && level.value >= 3);
watch(mapAvailable, (ok) => {
  if (!ok && view.value === "map") view.value = "coach"; // carte masquée aux niveaux 1 et 2 : rien à dévoiler
});
// Nouvelles zones prêtes mais pas encore vues : un point sur l'onglet Carte (le travail de fond se voit).
const mapUnseen = ref(false);
watch(
  () => [engine.current?.id, engine.current?.cloud.status],
  () => {
    if (engine.current?.cloud.status === "done" && view.value !== "map") mapUnseen.value = true;
    if (engine.current?.cloud.status !== "done") mapUnseen.value = false;
  },
);
watch(view, (v) => {
  if (v === "map") mapUnseen.value = false;
});
// Barre d'onglets du bas : la navigation ; les niveaux d'aide, en haut, dosent l'aide.
const tabs = computed(() => [
  { id: "coach" as const, label: "Coach", disabled: false, hint: "" },
  ...(engine.map.enabled
    ? [{ id: "map" as const, label: "Carte", disabled: !mapAvailable.value || !engine.current,
         hint: !mapAvailable.value ? "À partir du niveau 3 (Pays) : la carte dévoile les pays."
           : engine.current ? "" : "Fais d'abord une capture." }]
    : []),
  { id: "settings" as const, label: "Réglages", disabled: false, hint: "" },
]);
</script>

<template>
  <!-- La carte profite de toute la largeur si la fenêtre est agrandie ; le coach reste en colonne lisible. -->
  <div class="mx-auto flex min-h-screen flex-col px-4 pt-4" :class="view === 'map' ? 'max-w-none' : 'max-w-xl'">
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
      <SettingsPanel />
    </main>

    <main v-else-if="view === 'map' && engine.current && mapAvailable" class="flex min-h-0 flex-1 flex-col pt-3">
      <CoachMap :key="engine.current.id" :analysis="engine.current" :level="level" />
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

    <nav
      class="sticky bottom-0 z-[1100] -mx-4 mt-6 grid border-t border-courbe-fonce bg-encre px-2 pb-[env(safe-area-inset-bottom)]"
      :style="{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }"
      aria-label="Vues du coach"
    >
      <button
        v-for="t in tabs"
        :key="t.id"
        type="button"
        class="border-t-2 py-2.5 text-[0.95rem] font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-40 motion-reduce:transition-none"
        :class="view === t.id ? 'border-papier text-papier' : 'border-transparent text-courbe hover:text-papier'"
        :aria-current="view === t.id ? 'page' : undefined"
        :disabled="t.disabled"
        :title="t.hint"
        @click="view = t.id"
      >
        {{ t.label }}<span
          v-if="t.id === 'map' && mapUnseen && !t.disabled"
          class="ml-1.5 inline-block size-2 rounded-full bg-lac align-middle"
          aria-label="nouvelles zones"
        />
      </button>
    </nav>
  </div>
</template>
