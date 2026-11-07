<script setup lang="ts">
// Écran Réglages : tout ce qui s'applique à chaud. Le reste (adresse de l'API, recadrage, prompts)
// se règle dans ~/.config/geonesclick/config.toml.
import { onMounted, ref } from "vue";
import type { Settings } from "../engine";
import { engine, fr, getJSON, saveSettings, testModel } from "../engine";

const emit = defineEmits<{ close: [] }>();

const s = ref<Settings | null>(null);
const models = ref<string[]>([]);
const saved = ref<string | null>(null);
const test = ref<{ model: string; text: string; ok: boolean } | null>(null);
const testing = ref(false);

onMounted(async () => {
  s.value = await getJSON<Settings>("/settings");
  models.value = (await getJSON<{ models: string[] }>("/models"))?.models ?? [];
});

async function runTest() {
  if (!s.value) return;
  const model = String(s.value.vision.model);
  testing.value = true;
  const r = await testModel(model);
  testing.value = false;
  test.value = r.ok
    ? { model, ok: true, text: `Accepte les images, répond en ${fr(r.seconds ?? 0)} s.` }
    : { model, ok: false, text: r.error ?? "Échec du test." };
}

async function submit() {
  if (!s.value) return;
  saved.value = null;
  const error = await saveSettings(s.value);
  saved.value = error ?? "Réglages enregistrés et appliqués.";
}

const field = "mt-1 w-full rounded-md border border-courbe-fonce bg-relief px-3 py-2 text-papier";
const check = "size-4 accent-[var(--color-foret)]";
</script>

<template>
  <section aria-labelledby="reglages-titre" class="pt-4">
    <header class="flex items-baseline justify-between">
      <h2 id="reglages-titre" class="atlas text-[1.6rem] text-papier">Réglages</h2>
      <button type="button" class="text-[0.9rem] text-courbe underline underline-offset-4 hover:text-papier" @click="emit('close')">
        Retour au coach
      </button>
    </header>

    <p v-if="!s" class="mt-4 text-courbe">Chargement des réglages…</p>

    <form v-else class="mt-4 space-y-7" @submit.prevent="submit">
      <fieldset class="space-y-3">
        <legend class="font-bold text-papier">Niveaux d'aide</legend>
        <label class="flex items-start gap-3">
          <input v-model="s.coach.default_level" type="radio" :value="1" :class="check" class="mt-1" />
          <span>Commencer par le niveau 1 <span class="block text-[0.85rem] text-courbe">Les observations de l'IA attendent ton clic.</span></span>
        </label>
        <label class="flex items-start gap-3">
          <input v-model="s.coach.default_level" type="radio" :value="2" :class="check" class="mt-1" />
          <span>Tout montrer <span class="block text-[0.85rem] text-courbe">Les observations s'affichent dès qu'elles arrivent.</span></span>
        </label>
        <label class="flex items-start gap-3">
          <input v-model="s.coach.reveal_countries" type="checkbox" :class="check" class="mt-1" />
          <span>Montrer les pays probables d'emblée <span class="block text-[0.85rem] text-courbe">Sinon, le coach montre d'abord où regarder.</span></span>
        </label>
      </fieldset>

      <fieldset class="space-y-3">
        <legend class="font-bold text-papier">Modèle de vision (niveau 2)</legend>
        <label class="flex items-center gap-3">
          <input v-model="s.vision.enabled" type="checkbox" :class="check" />
          Activer le niveau 2
        </label>
        <label class="block">
          <span class="text-[0.85rem] text-courbe">Modèle NVIDIA ({{ models.length || "liste indisponible" }} disponibles)</span>
          <input v-model="s.vision.model" list="modeles" :class="field" spellcheck="false" />
          <datalist id="modeles">
            <option v-for="m in models" :key="m" :value="m" />
          </datalist>
        </label>
        <div class="flex flex-wrap items-center gap-3">
          <button
            type="button"
            class="rounded-md border border-lac/50 px-3 py-1.5 text-papier hover:bg-lac/10 disabled:opacity-50"
            :disabled="testing"
            @click="runTest"
          >
            {{ testing ? "Test en cours…" : "Tester ce modèle" }}
          </button>
          <p v-if="test && test.model === s.vision.model" class="text-[0.85rem]" :class="test.ok ? 'text-foret' : 'text-alerte'" role="status">
            {{ test.text }}
          </p>
        </div>
        <label class="flex items-center gap-3">
          <input v-model="s.vision.thinking" type="checkbox" :class="check" />
          Laisser le modèle raisonner (plus lent)
        </label>
        <label class="block max-w-48">
          <span class="text-[0.85rem] text-courbe">Délai maximal (secondes)</span>
          <input v-model.number="s.vision.timeout_s" type="number" min="5" max="300" :class="field" />
        </label>
      </fieldset>

      <fieldset class="space-y-3">
        <legend class="font-bold text-papier">Où regarder (niveau 1)</legend>
        <label class="flex items-center gap-3">
          <input v-model="s.metas.include_seed" type="checkbox" :class="check" />
          Utiliser l'amorce de metas (faits établis, non vérifiés)
        </label>
        <label class="flex items-center gap-3">
          <input v-model="s.metas.judge_buttons" type="checkbox" :class="check" :disabled="!s.metas.include_seed" />
          Boutons « Juste » / « Faux » pour vérifier l'amorce
        </label>
        <label class="flex items-center gap-3">
          <input v-model="s.metas.show_looks" type="checkbox" :class="check" />
          Dire quoi observer avant de révéler les pays
        </label>
        <p class="text-[0.85rem]" :class="engine.metas.message.startsWith('metas indisponibles') ? 'text-alerte' : 'text-courbe'">
          {{ engine.metas.message }}
        </p>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-[0.85rem] text-courbe">Catégories affichées</span>
            <input v-model.number="s.metas.max_categories" type="number" min="1" max="12" :class="field" />
          </label>
          <label class="block">
            <span class="text-[0.85rem] text-courbe">Pays probables listés</span>
            <input v-model.number="s.streetclip.top_k" type="number" min="1" max="20" :class="field" />
          </label>
        </div>
      </fieldset>

      <fieldset v-if="engine.dataset.enabled" class="space-y-3">
        <legend class="font-bold text-papier">Après la manche</legend>
        <label class="flex items-start gap-3">
          <input v-model="s.dataset.ask_guessed" type="checkbox" :class="check" class="mt-1" />
          <span>Demander le pays que j'avais répondu <span class="block text-[0.85rem] text-courbe">Sinon, un simple « Tu l'avais trouvé ? » Oui / Non.</span></span>
        </label>
        <label class="block max-w-48">
          <span class="text-[0.85rem] text-courbe">Confusions affichées (0 = aucune)</span>
          <input v-model.number="s.dataset.max_confusions" type="number" min="0" max="10" :class="field" :disabled="!s.dataset.ask_guessed" />
        </label>
      </fieldset>

      <fieldset class="space-y-3">
        <legend class="font-bold text-papier">Captures</legend>
        <label class="flex items-center gap-3">
          <input v-model="s.capture.notify" type="checkbox" :class="check" />
          Notification à chaque capture
        </label>
        <label class="flex items-center gap-3">
          <input v-model="s.capture.sound" type="checkbox" :class="check" :disabled="!s.capture.notify" />
          Avec un son
        </label>
        <label class="flex items-center gap-3">
          <input v-model="s.capture.save_to_disk" type="checkbox" :class="check" />
          Garder une copie des captures sur le disque
        </label>
        <label class="block max-w-48">
          <span class="text-[0.85rem] text-courbe">Nombre de captures gardées (0 = toutes)</span>
          <input v-model.number="s.capture.keep_last" type="number" min="0" :class="field" :disabled="!s.capture.save_to_disk" />
        </label>
      </fieldset>

      <div class="flex flex-wrap items-center gap-4 border-t border-courbe-fonce pt-4">
        <button type="submit" class="rounded-md bg-papier px-4 py-2 font-bold text-encre hover:bg-white disabled:opacity-40" :disabled="engine.busy">
          Enregistrer
        </button>
        <p v-if="saved" class="text-[0.9rem] text-papier" role="status">{{ saved }}</p>
      </div>

      <p class="text-[0.85rem] text-courbe">
        Adresse de l'API, recadrage, prompts, liste des pays, consignes et poids des catégories se modifient dans
        ~/.config/geonesclick/config.toml. Cet écran n'y écrit que les valeurs que tu changes, en
        conservant tes commentaires.
      </p>
    </form>
  </section>
</template>
