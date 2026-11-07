<script setup lang="ts">
// Un réglage de l'écran Réglages, rendu selon son type (settingsSchema.ts). Il ne sauve rien lui-même :
// il émet la nouvelle valeur (« save ») ou une erreur de saisie (« invalid »), et l'écran s'en charge.
import { computed, reactive } from "vue";
import type { Settings } from "../engine";
import { CATEGORY_LABELS, countryName, flag } from "../engine";
import type { Field } from "../settingsSchema";

const props = defineProps<{
  field: Field;
  settings: Settings;
  status?: { tone: "ok" | "error" | "busy"; text: string };
}>();
const emit = defineEmits<{
  save: [section: string, key: string, value: unknown];
  invalid: [text: string];
}>();

const f = computed(() => props.field);
const value = computed(() => props.settings[f.value.section]?.[f.value.key]);
const disabled = computed(() => !!f.value.needs && !props.settings[f.value.needs[0]]?.[f.value.needs[1]]);
const save = (v: unknown, section = f.value.section, key = f.value.key) => emit("save", section, key, v);
const inputId = computed(() => `reglage-${f.value.section}-${f.value.key}`);

function number(raw: string) {
  const n = Number(raw.replace(",", "."));
  if (raw.trim() === "" || !Number.isFinite(n)) return emit("invalid", "Un nombre est attendu.");
  if (f.value.kind === "int" && !Number.isInteger(n)) return emit("invalid", "Un nombre entier est attendu.");
  save(n);
}

// --- Rectangles en fractions [gauche, haut, droite, bas] ------------------------------------------------
const rectText = (r: unknown) => (Array.isArray(r) && r.length ? r.join(", ") : "");
function parseRect(text: string): number[] | null {
  const parts = text.split(/[,;\s]+/).filter(Boolean).map(Number);
  return parts.length === 4 && parts.every(Number.isFinite) ? parts : null;
}
function saveRect(text: string) {
  if (!text.trim()) return save([]);
  const r = parseRect(text);
  return r ? save(r) : emit("invalid", "Quatre nombres attendus : gauche, haut, droite, bas.");
}
function saveRects(text: string) {
  const rects = text.split("\n").map((l) => l.trim()).filter(Boolean).map(parseRect);
  return rects.every((r) => r) ? save(rects) : emit("invalid", "Chaque ligne : quatre nombres (gauche, haut, droite, bas).");
}

// --- Une valeur par catégorie de metas ----------------------------------------------------------------
const CATEGORIES = Object.entries(CATEGORY_LABELS);
const dict = computed(() => (value.value ?? {}) as Record<string, unknown>);
const categoryValue = (c: string) => {
  const v = dict.value[c];
  return Array.isArray(v) ? v.join(", ") : v === undefined ? "" : String(v);
};
function saveCategory(c: string, raw: string) {
  const next = { ...dict.value };
  const text = raw.trim();
  if (!text) delete next[c];
  else if (f.value.kind === "categoryNumber") {
    const n = Number(text.replace(",", "."));
    if (!Number.isFinite(n) || n < 0) return emit("invalid", "Un nombre positif ou nul est attendu.");
    next[c] = n;
  } else if (f.value.kind === "categoryList") next[c] = text.split(",").map((w) => w.trim()).filter(Boolean);
  else next[c] = text;
  save(next);
}

// --- Pays candidats : cocher pour garder, décocher pour écarter, ajouter -------------------------------
const countries = computed(() =>
  Object.entries((props.settings.streetclip?.countries ?? {}) as Record<string, string>)
    .map(([name, code]) => ({ name, code }))
    .sort((a, b) => countryName(a.code).localeCompare(countryName(b.code), "fr")),
);
const excluded = computed(() => (props.settings.streetclip?.exclude_countries ?? []) as string[]);
const toggle = (code: string, keep: boolean) =>
  save(keep ? excluded.value.filter((c) => c !== code) : [...excluded.value, code], "streetclip", "exclude_countries");
const added = reactive({ name: "", code: "" });
function addCountry() {
  const name = added.name.trim();
  const code = added.code.trim().toUpperCase();
  if (!/^[A-Za-z][A-Za-z .'-]{1,60}$/.test(name) || !/^[A-Z]{2}$/.test(code)) {
    return emit("invalid", "Nom anglais du pays et code ISO à deux lettres attendus.");
  }
  save({ ...(value.value as Record<string, string>), [name]: code });
  Object.assign(added, { name: "", code: "" });
}

const input = "mt-1 w-full rounded-md border border-courbe-fonce bg-relief px-3 py-2 text-papier disabled:opacity-50";
const check = "mt-1 size-4 shrink-0 accent-[var(--color-foret)] disabled:opacity-50";
const TONE = { ok: "text-foret", error: "text-alerte", busy: "text-courbe" };
</script>

<template>
  <div :class="disabled ? 'opacity-60' : ''">
    <!-- Case à cocher -->
    <label v-if="f.kind === 'bool'" class="flex items-start gap-3">
      <input type="checkbox" :class="check" :checked="!!value" :disabled="disabled"
             @change="save(($event.target as HTMLInputElement).checked)" />
      <span>{{ f.label }}<span v-if="f.hint" class="block text-[0.85rem] text-courbe">{{ f.hint }}</span></span>
    </label>

    <!-- Choix exclusif -->
    <fieldset v-else-if="f.kind === 'radio'" class="space-y-2" :disabled="disabled">
      <legend>{{ f.label }}<span v-if="f.hint" class="block text-[0.85rem] text-courbe">{{ f.hint }}</span></legend>
      <label v-for="o in f.options" :key="o.value" class="flex items-start gap-3">
        <input type="radio" :name="inputId" :class="check" :checked="value === o.value" @change="save(o.value)" />
        <span>{{ o.label }}<span v-if="o.hint" class="block text-[0.85rem] text-courbe">{{ o.hint }}</span></span>
      </label>
    </fieldset>

    <!-- Pays candidats -->
    <div v-else-if="f.kind === 'countries'">
      <p>{{ f.label }} <span class="text-courbe">({{ countries.length - excluded.length }} / {{ countries.length }})</span></p>
      <p v-if="f.hint" class="text-[0.85rem] text-courbe">{{ f.hint }}</p>
      <details class="mt-2">
        <summary class="cursor-pointer text-[0.9rem] text-courbe hover:text-papier">Voir et modifier la liste</summary>
        <ul class="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
          <li v-for="c in countries" :key="c.code">
            <label class="flex items-center gap-2 text-[0.9rem]">
              <input type="checkbox" :class="check" class="mt-0" :checked="!excluded.includes(c.code)"
                     @change="toggle(c.code, ($event.target as HTMLInputElement).checked)" />
              <span class="truncate">{{ flag(c.code) }} {{ countryName(c.code) }}</span>
            </label>
          </li>
        </ul>
        <form class="mt-3 flex flex-wrap items-end gap-2" @submit.prevent="addCountry">
          <label class="min-w-0 flex-1">
            <span class="text-[0.85rem] text-courbe">Nom anglais (utilisé dans le prompt)</span>
            <input v-model="added.name" :class="input" placeholder="Laos" maxlength="60" />
          </label>
          <label class="w-20">
            <span class="text-[0.85rem] text-courbe">Code</span>
            <input v-model="added.code" :class="input" placeholder="LA" maxlength="2" />
          </label>
          <button type="submit" class="rounded-md border border-foret/50 px-3 py-2 text-papier hover:bg-foret/10">Ajouter</button>
        </form>
      </details>
    </div>

    <!-- Une valeur par catégorie -->
    <div v-else-if="f.kind === 'categoryText' || f.kind === 'categoryNumber' || f.kind === 'categoryList'">
      <p>{{ f.label }}</p>
      <p v-if="f.hint" class="text-[0.85rem] text-courbe">{{ f.hint }}</p>
      <div class="mt-2 grid gap-2" :class="f.kind === 'categoryNumber' ? 'grid-cols-2' : 'grid-cols-1'">
        <label v-for="[c, label] in CATEGORIES" :key="c" class="block">
          <span class="text-[0.85rem] text-courbe">{{ label }}</span>
          <input :class="input" :value="categoryValue(c)" :inputmode="f.kind === 'categoryNumber' ? 'decimal' : 'text'"
                 @change="saveCategory(c, ($event.target as HTMLInputElement).value)" />
        </label>
      </div>
    </div>

    <!-- Champs simples -->
    <label v-else class="block">
      <span>{{ f.label }}</span>
      <span v-if="f.hint" class="block text-[0.85rem] text-courbe">{{ f.hint }}</span>
      <select v-if="f.kind === 'select'" :id="inputId" :class="input" :value="value" :disabled="disabled"
              @change="save(($event.target as HTMLSelectElement).value)">
        <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <input v-else-if="f.kind === 'int' || f.kind === 'float'" :id="inputId" type="number" :class="[input, 'max-w-48']"
             :min="f.min" :max="f.max" :step="f.step ?? (f.kind === 'int' ? 1 : 'any')" :value="value" :disabled="disabled"
             @change="number(($event.target as HTMLInputElement).value)" />
      <input v-else-if="f.kind === 'rect'" :id="inputId" :class="input" :value="rectText(value)" placeholder="image entière"
             :disabled="disabled" @change="saveRect(($event.target as HTMLInputElement).value)" />
      <textarea v-else-if="f.kind === 'rects'" :id="inputId" :class="input" rows="3" :value="(value as unknown[]).map(rectText).join('\n')"
                :disabled="disabled" spellcheck="false" @change="saveRects(($event.target as HTMLTextAreaElement).value)" />
      <textarea v-else-if="f.kind === 'textarea'" :id="inputId" :class="[input, 'font-mono text-[0.8rem]']" rows="10"
                :value="String(value ?? '')" :disabled="disabled" spellcheck="false"
                @change="save(($event.target as HTMLTextAreaElement).value)" />
      <input v-else :id="inputId" :class="input" :value="String(value ?? '')" :disabled="disabled" spellcheck="false"
             :list="f.section === 'vision' && f.key === 'model' ? 'modeles-nvidia' : undefined"
             @change="save(($event.target as HTMLInputElement).value.trim())" />
    </label>

    <p v-if="status" class="mt-1 text-[0.85rem]" :class="TONE[status.tone]" role="status">{{ status.text }}</p>
  </div>
</template>
