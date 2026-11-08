<script setup lang="ts">
// Marks window: the frozen view in full screen, where the player circles each clue (street sign,
// road sign, shop sign…). Created hidden at startup (tauri.conf.json) to show without delay; it listens to the
// engine and shows up on each "freeze" (Super+Shift+Z or the "Mark" button).
import { getCurrentWindow } from "@tauri-apps/api/window";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ENGINE_URL, WS_URL } from "./engine";

type Rect = [number, number, number, number]; // fractions [left, top, right, bottom] of the raw image
const MIN_PX = 8; // a single click does not make a mark

const win = getCurrentWindow();
const open = ref(false);
const freezeId = ref("");
const image = ref("");
const size = ref({ width: 16, height: 9 });
const targetAt = ref(""); // time of the analysis the marks complete (the current round)
const existing = ref(0); // marks already placed in this round: numbering continues
const max = ref(9);
const uses = ref<string[]>([]); // what the coach draws from a mark (provided by the engine)
const notYet = ref<string[]>([]);
const rects = ref<Rect[]>([]);
const drawing = ref<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
const sending = ref(false);
const error = ref<string | null>(null);
const stage = ref<HTMLElement | null>(null);

const firstNumber = computed(() => existing.value + 1);
const roundTime = computed(() => (targetAt.value ? new Date(targetAt.value).toLocaleTimeString("fr-FR") : ""));
const full = computed(() => rects.value.length >= max.value);

async function post<T>(path: string, body: unknown): Promise<{ ok: boolean; data: T | null; detail: string }> {
  try {
    const res = await fetch(ENGINE_URL + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => null);
    const detail = typeof data?.detail === "string" ? data.detail : `le moteur a répondu ${res.status}`;
    return { ok: res.ok, data: res.ok ? (data as T) : null, detail };
  } catch {
    return { ok: false, data: null, detail: "le moteur ne répond pas" };
  }
}

async function show(msg: { id: string; width: number; height: number; target_at: string; marks: number }) {
  Object.assign(size.value, { width: msg.width, height: msg.height });
  freezeId.value = msg.id;
  targetAt.value = msg.target_at;
  existing.value = msg.marks;
  rects.value = [];
  drawing.value = null;
  error.value = null;
  image.value = "";
  open.value = true;
  try {
    await win.show();
    await win.setFullscreen(true);
    await win.setFocus(); // GNOME may withhold the keyboard: the buttons stay there to confirm or cancel
  } catch {
    /* window already visible */
  }
  const res = await post<{ image: string }>("/marks/frame", { id: msg.id });
  if (res.data && freezeId.value === msg.id) image.value = res.data.image;
  else if (!res.ok) error.value = `Vue figée indisponible : ${res.detail}.`;
}

async function close() {
  open.value = false;
  image.value = ""; // frees the image (several MB) while the window is hidden
  rects.value = [];
  try {
    await win.hide();
  } catch {
    /* already hidden */
  }
}

async function submit() {
  if (!rects.value.length || sending.value) return;
  sending.value = true;
  const res = await post("/marks", { id: freezeId.value, rects: rects.value });
  sending.value = false;
  if (res.ok) await close();
  else error.value = `Marques refusées : ${res.detail}.`;
}

const removeLast = () => void rects.value.pop();

// --- drawing -------------------------------------------------------------------------------------
function point(e: PointerEvent) {
  const box = stage.value!.getBoundingClientRect();
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  return { x: clamp((e.clientX - box.left) / box.width), y: clamp((e.clientY - box.top) / box.height), box };
}
function down(e: PointerEvent) {
  if (e.button !== 0 || full.value || !image.value) return;
  const { x, y } = point(e);
  drawing.value = { x0: x, y0: y, x1: x, y1: y };
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
}
function move(e: PointerEvent) {
  if (!drawing.value) return;
  const { x, y } = point(e);
  Object.assign(drawing.value, { x1: x, y1: y });
}
function up(e: PointerEvent) {
  const d = drawing.value;
  drawing.value = null;
  if (!d) return;
  const { box } = point(e);
  const [l, r] = [Math.min(d.x0, d.x1), Math.max(d.x0, d.x1)];
  const [t, b] = [Math.min(d.y0, d.y1), Math.max(d.y0, d.y1)];
  if ((r - l) * box.width >= MIN_PX && (b - t) * box.height >= MIN_PX) rects.value.push([l, t, r, b]);
}
const live = computed<Rect | null>(() => {
  const d = drawing.value;
  return d ? [Math.min(d.x0, d.x1), Math.min(d.y0, d.y1), Math.max(d.x0, d.x1), Math.max(d.y0, d.y1)] : null;
});
const boxStyle = (r: Rect) => ({
  left: `${r[0] * 100}%`, top: `${r[1] * 100}%`, width: `${(r[2] - r[0]) * 100}%`, height: `${(r[3] - r[1]) * 100}%`,
});

function key(e: KeyboardEvent) {
  if (!open.value) return;
  if (e.key === "Escape") void close();
  else if (e.key === "Enter") void submit();
  else if (e.key === "Backspace" || e.key === "Delete" || (e.key === "z" && e.ctrlKey)) removeLast();
  else return;
  e.preventDefault();
}

// --- listening to the engine ---------------------------------------------------------------------
let ws: WebSocket | null = null;
let retry: ReturnType<typeof setTimeout> | undefined;
function listen() {
  ws = new WebSocket(WS_URL);
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "state") {
      max.value = msg.marks?.max ?? max.value;
      uses.value = msg.marks?.uses ?? [];
      notYet.value = msg.marks?.not_yet ?? [];
    }
    else if (msg.type === "freeze") void show(msg);
  };
  ws.onclose = () => {
    retry = setTimeout(listen, 1500);
  };
}
onMounted(() => {
  listen();
  window.addEventListener("keydown", key);
});
onBeforeUnmount(() => {
  clearTimeout(retry);
  if (ws) ws.onclose = null;
  ws?.close();
  window.removeEventListener("keydown", key);
});
</script>

<template>
  <div v-if="open" class="fixed inset-0 grid select-none place-items-center bg-black">
    <!-- The image keeps its aspect ratio: the rectangles' fractions are those of the raw image. -->
    <div
      ref="stage"
      class="relative cursor-crosshair touch-none"
      :style="{ aspectRatio: `${size.width} / ${size.height}`, width: `min(100vw, 100vh * ${size.width / size.height})` }"
      @pointerdown="down"
      @pointermove="move"
      @pointerup="up"
      @pointercancel="drawing = null"
      @contextmenu.prevent="removeLast"
    >
      <img v-if="image" :src="image" alt="Vue figée" class="pointer-events-none size-full" draggable="false" />
      <p v-else-if="!error" class="absolute inset-0 grid place-items-center text-courbe">Vue figée…</p>
      <div
        v-for="(r, i) in rects"
        :key="i"
        class="absolute border-2 border-marque shadow-[0_0_0_1px_rgb(0_0_0/0.6)]"
        :style="boxStyle(r)"
      >
        <span class="absolute -top-3.5 -left-3.5 grid size-7 place-items-center rounded-full bg-marque text-[0.9rem] font-bold text-encre">
          {{ firstNumber + i }}
        </span>
      </div>
      <div v-if="live" class="absolute border-2 border-dashed border-marque" :style="boxStyle(live)" />
    </div>

    <!-- Toolbar: fades out while drawing so it hides nothing of the view. -->
    <div
      class="fixed top-3 left-1/2 flex max-w-[calc(100vw-2rem)] -translate-x-1/2 flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-courbe-fonce bg-encre/90 px-4 py-2.5 text-[0.95rem] text-papier shadow-lg transition-opacity motion-reduce:transition-none"
      :class="drawing ? 'pointer-events-none opacity-0' : 'opacity-100'"
    >
      <p class="min-w-0">
        <template v-if="error"><span class="text-alerte" role="alert">{{ error }}</span></template>
        <template v-else-if="full">{{ max }} marques au plus : valide ou retire la dernière.</template>
        <template v-else>Entoure chaque indice : plaque de rue, panneau, enseigne…</template>
        <span class="ml-2 text-courbe">{{ rects.length }} / {{ max }}</span>
      </p>
      <p class="text-courbe" title="Nouvelle manche ? Annule, capture (Super+Maj+G), puis marque.">
        Complète la manche capturée à {{ roundTime }}
      </p>
      <div class="flex gap-2">
        <button
          type="button"
          class="rounded-md border border-courbe-fonce px-3 py-1.5 text-courbe hover:text-papier"
          :disabled="!rects.length"
          @click="removeLast"
        >
          Retirer la dernière
        </button>
        <button type="button" class="rounded-md border border-courbe-fonce px-3 py-1.5 text-papier hover:bg-relief" @click="close">
          Annuler <kbd class="text-courbe">Échap</kbd>
        </button>
        <button
          type="button"
          class="rounded-md bg-marque px-3 py-1.5 font-bold text-encre hover:brightness-110 disabled:opacity-40"
          :disabled="!rects.length || sending"
          @click="submit"
        >
          Lire les marques <kbd class="font-normal">Entrée</kbd>
        </button>
      </div>
      <!-- What the coach draws from a mark: to know what to circle, and what does not count yet. -->
      <dl v-if="uses.length || notYet.length" class="w-full border-t border-courbe-fonce pt-2 text-[0.85rem]">
        <div v-if="uses.length" class="flex gap-2">
          <dt class="shrink-0 text-marque">Pris en compte</dt>
          <dd class="text-papier">{{ uses.join(" ; ") }}.</dd>
        </div>
        <div v-if="notYet.length" class="mt-0.5 flex gap-2">
          <dt class="shrink-0 text-courbe">Pas encore</dt>
          <dd class="text-courbe">{{ notYet.join(" ; ") }}.</dd>
        </div>
      </dl>
    </div>
  </div>
</template>
