<script setup lang="ts">
// Settings › Storage: what the coach keeps on disk, the size of each item, and "Empty".
// Emptying takes two steps (Empty → Confirm, with what it costs): nothing goes on a stray click.
// The test set, your metas and your config are not listed: they are never emptied.
import { computed, onMounted, ref } from "vue";
import type { EraseGroup } from "../engine";
import { clearStorage, engine, erasePlan, eraseEverything, fr, getJSON } from "../engine";

interface Item {
  id: string;
  label: string;
  kind: "cache" | "socle" | "historique";
  size: number;
  detail: string;
  effect: string;
  confirm: boolean;
}
const props = defineProps<{ maxMb: number }>();
const items = ref<Item[] | null>(null);
const asking = ref<string | null>(null); // item awaiting confirmation
const busy = ref(false);
const done = ref<string | null>(null);

const KIND: Record<Item["kind"], string> = {
  cache: "cache limité", socle: "socle, vidé à la main seulement", historique: "historique",
};
const size = (bytes: number) =>
  bytes >= 1024 ** 3 ? `${fr(bytes / 1024 ** 3)} Go` : bytes >= 1024 ** 2 ? `${fr(bytes / 1024 ** 2)} Mo`
    : `${fr(bytes / 1024)} Ko`;
const total = computed(() => (items.value ?? []).reduce((n, i) => n + i.size, 0));
const growing = computed(() => (items.value ?? []).filter((i) => i.kind === "cache").reduce((n, i) => n + i.size, 0));

async function load() {
  items.value = (await getJSON<{ items: Item[] }>("/storage"))?.items ?? [];
}
onMounted(load);

// "Erase everything" (right to erasure, GDPR): the list with the sizes, the word EFFACER to type, then the engine
// and the UI start again from scratch. The models (nothing personal) only if the box is ticked.
const erase = ref<EraseGroup[] | null>(null);
const typed = ref("");
const withModels = ref(false);
const erasing = ref(false);
const eraseError = ref<string | null>(null);
async function openErase() {
  erase.value = (await erasePlan())?.groups ?? [];
  typed.value = "";
  withModels.value = false;
  eraseError.value = null;
}
const eraseTotal = computed(() =>
  (erase.value ?? []).filter((g) => !g.optional || withModels.value).reduce((n, g) => n + g.size, 0));
async function confirmErase() {
  erasing.value = true;
  eraseError.value = await eraseEverything(withModels.value);
  erasing.value = false;
}

async function clear(item: Item) {
  busy.value = true;
  const res = await clearStorage(item.id);
  busy.value = false;
  asking.value = null;
  if (res) {
    items.value = res.items as Item[];
    done.value = `${item.label} : ${size(res.freed)} libérés.`;
  }
}
</script>

<template>
  <div class="space-y-3">
    <p class="text-[0.85rem] text-courbe">
      Sur le disque : {{ size(total) }}. Caches qui grossissent : {{ size(growing) }} sur {{ fr(props.maxMb) }} Mo au plus
      (les moins récemment utilisés partent d'abord). « Vider » ne touche jamais ton jeu de test, tes metas ni ta config ;
      « Tout effacer », plus bas, oui.
    </p>
    <p v-if="!items" class="text-courbe">Mesure en cours…</p>
    <ul v-else class="space-y-3">
      <li v-for="item in items" :key="item.id" class="rounded-md border border-courbe-fonce/70 px-3 py-2">
        <div class="flex items-baseline gap-3">
          <p class="min-w-0 flex-1 text-papier">{{ item.label }}</p>
          <span class="shrink-0 tabular-nums text-papier">{{ size(item.size) }}</span>
        </div>
        <p class="text-[0.85rem] text-courbe">{{ item.detail }} · {{ KIND[item.kind] }}</p>
        <div v-if="asking === item.id" class="mt-2 space-y-2" role="alert">
          <p class="text-[0.85rem]" :class="item.confirm ? 'text-alerte' : 'text-papier'">{{ item.effect }}</p>
          <div class="flex gap-2">
            <button type="button" class="rounded-md border border-alerte/70 px-3 py-1.5 text-papier hover:bg-alerte/10 disabled:opacity-50"
                    :disabled="busy" @click="clear(item)">
              {{ busy ? "Suppression…" : "Confirmer" }}
            </button>
            <button type="button" class="rounded-md border border-courbe-fonce px-3 py-1.5 text-courbe hover:text-papier"
                    @click="asking = null">
              Garder
            </button>
          </div>
        </div>
        <button v-else type="button" class="mt-1.5 text-[0.85rem] text-courbe underline underline-offset-2 hover:text-papier disabled:opacity-40"
                :disabled="!item.size" @click="asking = item.id; done = null">
          Vider
        </button>
      </li>
    </ul>
    <p v-if="done" class="text-[0.85rem] text-foret" role="status">{{ done }}</p>

    <!-- Erase everything: full reset (GDPR) -->
    <div class="mt-6 rounded-md border border-alerte/50 px-3 py-3">
      <p class="font-bold text-papier">Tout effacer</p>
      <p class="mt-0.5 text-[0.85rem] text-courbe">
        Remet l'application à zéro : tout ce qui te concerne est supprimé de cet ordinateur, puis le premier lancement
        recommence. Seuls les fichiers de l'application partent, jamais un de tes dossiers.
      </p>
      <p v-if="engine.erased" class="mt-2 text-[0.85rem] text-alerte" role="status">
        Données effacées : relance l'application pour repartir de zéro.
      </p>
      <button v-else-if="!erase" type="button"
              class="mt-2 rounded-md border border-alerte/70 px-3 py-1.5 text-papier hover:bg-alerte/10" @click="openErase">
        Voir ce qui serait effacé…
      </button>
      <form v-else class="mt-2 space-y-2" @submit.prevent="confirmErase">
        <ul class="space-y-1 text-[0.9rem]">
          <li v-for="g in erase.filter((x) => !x.optional)" :key="g.id" class="flex items-baseline gap-3">
            <span class="min-w-0 flex-1" :class="g.precious ? 'text-alerte' : 'text-papier'">
              {{ g.label }}<template v-if="g.precious"> ⚠ précieux : la base de toutes les mesures, perdu</template>
            </span>
            <span class="shrink-0 tabular-nums text-courbe">{{ g.files ? size(g.size) : "rien" }}</span>
          </li>
          <li class="text-papier">État de l'interface et raccourcis GNOME de l'application</li>
        </ul>
        <label v-for="g in erase.filter((x) => x.optional)" :key="g.id" class="flex items-baseline gap-2 text-[0.9rem] text-papier">
          <input v-model="withModels" type="checkbox" :disabled="!g.files" />
          <span class="flex-1">Aussi les {{ g.label.toLowerCase() }} <span class="text-courbe">(rien de personnel ; retéléchargés au
            prochain lancement)</span></span>
          <span class="tabular-nums text-courbe">{{ g.files ? size(g.size) : "absents" }}</span>
        </label>
        <p class="text-[0.85rem] text-courbe">Total : {{ size(eraseTotal) }}. Irréversible.</p>
        <label class="block text-[0.9rem] text-papier">
          Tape <strong>EFFACER</strong> pour confirmer
          <input v-model="typed" type="text" autocomplete="off" spellcheck="false"
                 class="mt-1 w-full rounded-md border border-courbe-fonce bg-relief px-3 py-1.5 text-papier" />
        </label>
        <div class="flex gap-2">
          <button type="submit" :disabled="typed !== 'EFFACER' || erasing"
                  class="rounded-md border border-alerte bg-alerte/15 px-3 py-1.5 font-bold text-papier hover:bg-alerte/25 disabled:opacity-40">
            {{ erasing ? "Effacement…" : "Tout effacer" }}
          </button>
          <button type="button" class="rounded-md border border-courbe-fonce px-3 py-1.5 text-courbe hover:text-papier"
                  @click="erase = null">
            Annuler
          </button>
        </div>
        <p v-if="eraseError" class="text-[0.85rem] text-alerte" role="alert">{{ eraseError }}</p>
      </form>
    </div>
  </div>
</template>
