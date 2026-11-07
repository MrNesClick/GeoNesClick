<script setup lang="ts">
import { computed } from "vue";
import Candidates from "./components/Candidates.vue";
import Observations from "./components/Observations.vue";
import { engine, requestCapture, reselectWindow, restartSharing } from "./engine";

const status = computed(() => {
  if (!engine.connected) return { tone: "bg-courbe", text: "Démarrage du moteur…" };
  if (engine.capture.starting) return { tone: "bg-courbe", text: "Choisis la fenêtre du jeu à partager…" };
  if (!engine.capture.alive) return { tone: "bg-alerte", text: engine.capture.message };
  if (!engine.streetclip.ready) return { tone: "bg-courbe", text: "Chargement du modèle local…" };
  return { tone: "bg-foret", text: "Prêt. Capture avec Super+Maj+G." };
});
const time = (iso: string) => new Date(iso).toLocaleTimeString("fr-FR");
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

    <p v-if="engine.error" class="mt-3 border-l-2 border-alerte pl-3 text-[0.9rem] text-papier" role="alert">
      {{ engine.error }}
    </p>

    <main v-if="engine.current" class="flex-1">
      <Transition name="arrivee" appear mode="out-in">
        <div :key="engine.current.id" class="space-y-6 pt-4">
          <figure>
            <img
              :src="engine.current.thumbnail"
              alt="Vue analysée"
              class="w-full rounded-md border border-courbe-fonce"
            />
            <figcaption class="mt-1.5 text-[0.8rem] text-courbe">
              Capture de {{ time(engine.current.at) }}, en {{ engine.current.captureMs }} ms
            </figcaption>
          </figure>

          <Candidates :scores="engine.current.scores" :ms="engine.current.clipMs" />

          <Observations
            :vision="engine.current.vision"
            :revealed="engine.revealed"
            @reveal="engine.revealed = true"
          />
        </div>
      </Transition>
    </main>

    <main v-else class="flex flex-1 flex-col justify-center py-10">
      <p class="atlas text-[1.6rem] leading-snug text-papier">Une vue, quelques indices.</p>
      <p class="mt-3 max-w-[34ch] text-courbe">
        Pendant une manche, appuie sur <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">Super</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">Maj</kbd>
        <kbd class="rounded border border-courbe-fonce px-1.5 text-papier">G</kbd>
        : le coach te montre d'abord les pays probables, puis ce qu'il observe dans la vue.
      </p>
    </main>

    <footer class="mt-6 flex items-center justify-between gap-3 border-t border-courbe-fonce pt-3 text-[0.85rem] text-courbe">
      <span>Autre navigateur, écran ou résolution ?</span>
      <button
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
