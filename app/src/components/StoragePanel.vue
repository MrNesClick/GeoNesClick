<script setup lang="ts">
// Settings › Storage: what the coach keeps on disk, the size of each item, and "Empty".
// Emptying takes two steps (Empty → Confirm, with what it costs): nothing goes on a stray click.
// The test set, your metas and your config are not listed: they are never emptied.
import { computed, onMounted, reactive, ref } from "vue";
import type { EraseGroup } from "../engine";
import { clearStorage, engine, erasePlan, eraseEverything, num, getJSON } from "../engine";
import type { Key } from "../i18n";
import { t } from "../i18n";

interface Item {
  id: string;
  label: string;
  kind: "cache" | "base" | "history";
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

const kind = (k: Item["kind"]) => t(`storage.kind.${k}`);
const size = (bytes: number) =>
  bytes >= 1024 ** 3 ? t("unit.gb", { n: num(bytes / 1024 ** 3) }) : bytes >= 1024 ** 2 ? t("unit.mb", { n: num(bytes / 1024 ** 2) })
    : t("unit.kb", { n: num(bytes / 1024) });
const total = computed(() => (items.value ?? []).reduce((n, i) => n + i.size, 0));
const growing = computed(() => (items.value ?? []).filter((i) => i.kind === "cache").reduce((n, i) => n + i.size, 0));

async function load() {
  items.value = (await getJSON<{ items: Item[] }>("/storage"))?.items ?? [];
}
onMounted(load);

// "Erase everything" (right to erasure, GDPR): the list with the sizes, the confirmation word to type, then the engine
// and the UI start again from scratch. Each optional group has its own box: the models (nothing personal), and the
// engine installed by the AppImage (an uninstall: the app then only offers to close).
const erase = ref<EraseGroup[] | null>(null);
const typed = ref("");
const withOptional = reactive<Record<string, boolean>>({ models: false, engine: false });
const ALSO: Record<string, [Key, Key]> = {
  models: ["storage.also.models", "storage.also_note.models"],
  engine: ["storage.also.engine", "storage.also_note.engine"],
};
const erasing = ref(false);
const eraseError = ref<string | null>(null);
async function openErase() {
  erase.value = (await erasePlan())?.groups ?? [];
  typed.value = "";
  withOptional.models = withOptional.engine = false;
  eraseError.value = null;
}
const eraseTotal = computed(() =>
  (erase.value ?? []).filter((g) => !g.optional || withOptional[g.id]).reduce((n, g) => n + g.size, 0));
async function closeApp() {
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().close(); // closing the coach quits the app (lib.rs)
}
async function confirmErase() {
  erasing.value = true;
  eraseError.value = await eraseEverything(withOptional.models, withOptional.engine);
  erasing.value = false;
}

async function clear(item: Item) {
  busy.value = true;
  const res = await clearStorage(item.id);
  busy.value = false;
  asking.value = null;
  if (res) {
    items.value = res.items as Item[];
    done.value = t("storage.freed", { item: item.label, size: size(res.freed) });
  }
}
</script>

<template>
  <div class="space-y-3">
    <p class="text-[0.85rem] text-courbe">
      {{ t("storage.summary", { total: size(total), growing: size(growing), max: t("unit.mb", { n: num(props.maxMb) }) }) }}
    </p>
    <p v-if="!items" class="text-courbe">{{ t("storage.measuring") }}</p>
    <ul v-else class="space-y-3">
      <li v-for="item in items" :key="item.id" class="rounded-md border border-courbe-fonce/70 px-3 py-2">
        <div class="flex items-baseline gap-3">
          <p class="min-w-0 flex-1 text-papier">{{ item.label }}</p>
          <span class="shrink-0 tabular-nums text-papier">{{ size(item.size) }}</span>
        </div>
        <p class="text-[0.85rem] text-courbe">{{ item.detail }} · {{ kind(item.kind) }}</p>
        <div v-if="asking === item.id" class="mt-2 space-y-2" role="alert">
          <p class="text-[0.85rem]" :class="item.confirm ? 'text-alerte' : 'text-papier'">{{ item.effect }}</p>
          <div class="flex gap-2">
            <button type="button" class="rounded-md border border-alerte/70 px-3 py-1.5 text-papier hover:bg-alerte/10 disabled:opacity-50"
                    :disabled="busy" @click="clear(item)">
              {{ t(busy ? "storage.deleting" : "storage.confirm") }}
            </button>
            <button type="button" class="rounded-md border border-courbe-fonce px-3 py-1.5 text-courbe hover:text-papier"
                    @click="asking = null">
              {{ t("storage.keep") }}
            </button>
          </div>
        </div>
        <button v-else type="button" class="mt-1.5 text-[0.85rem] text-courbe underline underline-offset-2 hover:text-papier disabled:opacity-40"
                :disabled="!item.size" @click="asking = item.id; done = null">
          {{ t("storage.empty") }}
        </button>
      </li>
    </ul>
    <p v-if="done" class="text-[0.85rem] text-foret" role="status">{{ done }}</p>

    <!-- Erase everything: full reset (GDPR) -->
    <div class="mt-6 rounded-md border border-alerte/50 px-3 py-3">
      <p class="font-bold text-papier">{{ t("storage.erase_all") }}</p>
      <p class="mt-0.5 text-[0.85rem] text-courbe">
        {{ t("storage.erase_intro") }}
      </p>
      <div v-if="engine.uninstalled" class="mt-2 space-y-2" role="status">
        <p class="text-[0.9rem] text-papier">{{ t("storage.uninstalled") }}</p>
        <button type="button" class="rounded-md border border-courbe-fonce px-3 py-1.5 text-papier hover:bg-relief"
                @click="closeApp">
          {{ t("storage.close") }}
        </button>
      </div>
      <p v-else-if="engine.erased" class="mt-2 text-[0.85rem] text-alerte" role="status">
        {{ t("storage.erased") }}
      </p>
      <button v-else-if="!erase" type="button"
              class="mt-2 rounded-md border border-alerte/70 px-3 py-1.5 text-papier hover:bg-alerte/10" @click="openErase">
        {{ t("storage.see_what") }}
      </button>
      <form v-else class="mt-2 space-y-2" @submit.prevent="confirmErase">
        <ul class="space-y-1 text-[0.9rem]">
          <li v-for="g in erase.filter((x) => !x.optional)" :key="g.id" class="flex items-baseline gap-3">
            <span class="min-w-0 flex-1" :class="g.precious ? 'text-alerte' : 'text-papier'">
              {{ g.label }}<template v-if="g.precious">{{ t("storage.precious") }}</template>
            </span>
            <span class="shrink-0 tabular-nums text-courbe">{{ g.files ? size(g.size) : t("storage.nothing") }}</span>
          </li>
          <li class="text-papier">{{ t("storage.ui_state") }}</li>
        </ul>
        <label v-for="g in erase.filter((x) => x.optional && ALSO[x.id])" :key="g.id"
               class="flex items-baseline gap-2 text-[0.9rem] text-papier">
          <input v-model="withOptional[g.id]" type="checkbox" :disabled="!g.files" />
          <span class="flex-1">{{ t(ALSO[g.id][0]) }} <span class="text-courbe">{{ t(ALSO[g.id][1]) }}</span></span>
          <span class="tabular-nums text-courbe">{{ g.files ? size(g.size) : t("storage.absent") }}</span>
        </label>
        <p class="text-[0.85rem] text-courbe">{{ t("storage.total", { size: size(eraseTotal) }) }}</p>
        <label class="block text-[0.9rem] text-papier">
          {{ t("storage.type_before") }} <strong>{{ t("storage.confirm_word") }}</strong> {{ t("storage.type_after") }}
          <input v-model="typed" type="text" autocomplete="off" spellcheck="false"
                 class="mt-1 w-full rounded-md border border-courbe-fonce bg-relief px-3 py-1.5 text-papier" />
        </label>
        <div class="flex gap-2">
          <button type="submit" :disabled="typed.trim() !== t('storage.confirm_word') || erasing"
                  class="rounded-md border border-alerte bg-alerte/15 px-3 py-1.5 font-bold text-papier hover:bg-alerte/25 disabled:opacity-40">
            {{ t(erasing ? "storage.erasing" : "storage.erase_all") }}
          </button>
          <button type="button" class="rounded-md border border-courbe-fonce px-3 py-1.5 text-courbe hover:text-papier"
                  @click="erase = null">
            {{ t("storage.cancel") }}
          </button>
        </div>
        <p v-if="eraseError" class="text-[0.85rem] text-alerte" role="alert">{{ eraseError }}</p>
      </form>
    </div>
  </div>
</template>
