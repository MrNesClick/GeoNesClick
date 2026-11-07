<script setup lang="ts">
// Réglages › Stockage : ce que le coach garde sur le disque, la taille de chaque élément, et « Vider ».
// Vider se fait en deux temps (Vider → Confirmer, avec ce que ça coûte) : rien ne part sur un clic égaré.
// Le jeu de test, tes metas et ta config n'y figurent pas : ils ne sont jamais vidés.
import { computed, onMounted, ref } from "vue";
import { clearStorage, fr, getJSON } from "../engine";

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
const asking = ref<string | null>(null); // élément en attente de confirmation
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
      (les moins récemment utilisés partent d'abord). Ton jeu de test, tes metas et ta config ne sont jamais vidés.
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
  </div>
</template>
