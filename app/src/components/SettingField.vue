<script setup lang="ts">
// One setting of the Settings screen, rendered according to its type (settingsSchema.ts). It saves nothing itself:
// it emits the new value ("save") or an input error ("invalid"), and the screen handles it.
import { computed, reactive } from "vue";
import { i18n, t } from "../i18n";
import type { Settings } from "../engine";
import { CATEGORIES, categoryLabel, countryName, flag } from "../engine";
import type { Field } from "../settingsSchema";
import { fieldHint, fieldLabel, optionHint, optionLabel } from "../settingsSchema";

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
const inputId = computed(() => `setting-${f.value.section}-${f.value.key}`);
const label = computed(() => fieldLabel(f.value));
const hint = computed(() => fieldHint(f.value));

function number(raw: string) {
  const n = Number(raw.replace(",", "."));
  if (raw.trim() === "" || !Number.isFinite(n)) return emit("invalid", t("field.number"));
  if (f.value.kind === "int" && !Number.isInteger(n)) return emit("invalid", t("field.integer"));
  save(n);
}

// --- Rectangles as fractions [left, top, right, bottom] ------------------------------------------------
const rectText = (r: unknown) => (Array.isArray(r) && r.length ? r.join(", ") : "");
function parseRect(text: string): number[] | null {
  const parts = text.split(/[,;\s]+/).filter(Boolean).map(Number);
  return parts.length === 4 && parts.every(Number.isFinite) ? parts : null;
}
function saveRect(text: string) {
  if (!text.trim()) return save([]);
  const r = parseRect(text);
  return r ? save(r) : emit("invalid", t("field.rect"));
}
function saveRects(text: string) {
  const rects = text.split("\n").map((l) => l.trim()).filter(Boolean).map(parseRect);
  return rects.every((r) => r) ? save(rects) : emit("invalid", t("field.rects"));
}

// --- One value per metas category ---------------------------------------------------------------------
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
    if (!Number.isFinite(n) || n < 0) return emit("invalid", t("field.positive"));
    next[c] = n;
  } else if (f.value.kind === "categoryList") next[c] = text.split(",").map((w) => w.trim()).filter(Boolean);
  else next[c] = text;
  save(next);
}

// --- Candidate countries: tick to keep, untick to rule out, add ---------------------------------------
const countries = computed(() =>
  Object.entries((props.settings.streetclip?.countries ?? {}) as Record<string, string>)
    .map(([name, code]) => ({ name, code }))
    .sort((a, b) => countryName(a.code).localeCompare(countryName(b.code), i18n.lang)),
);
const excluded = computed(() => (props.settings.streetclip?.exclude_countries ?? []) as string[]);
const toggle = (code: string, keep: boolean) =>
  save(keep ? excluded.value.filter((c) => c !== code) : [...excluded.value, code], "streetclip", "exclude_countries");
const added = reactive({ name: "", code: "" });
function addCountry() {
  const name = added.name.trim();
  const code = added.code.trim().toUpperCase();
  if (!/^[A-Za-z][A-Za-z .'-]{1,60}$/.test(name) || !/^[A-Z]{2}$/.test(code)) {
    return emit("invalid", t("field.country_invalid"));
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
    <!-- Checkbox -->
    <label v-if="f.kind === 'bool'" class="flex items-start gap-3">
      <input type="checkbox" :class="check" :checked="!!value" :disabled="disabled"
             @change="save(($event.target as HTMLInputElement).checked)" />
      <span>{{ label }}<span v-if="hint" class="block text-[0.85rem] text-courbe">{{ hint }}</span></span>
    </label>

    <!-- Exclusive choice -->
    <fieldset v-else-if="f.kind === 'radio'" class="space-y-2" :disabled="disabled">
      <legend>{{ label }}<span v-if="hint" class="block text-[0.85rem] text-courbe">{{ hint }}</span></legend>
      <label v-for="o in f.options" :key="o" class="flex items-start gap-3">
        <input type="radio" :name="inputId" :class="check" :checked="value === o" @change="save(o)" />
        <span>{{ optionLabel(f, o) }}<span v-if="optionHint(f, o)" class="block text-[0.85rem] text-courbe">{{ optionHint(f, o) }}</span></span>
      </label>
    </fieldset>

    <!-- Candidate countries -->
    <div v-else-if="f.kind === 'countries'">
      <p>{{ label }} <span class="text-courbe">({{ countries.length - excluded.length }} / {{ countries.length }})</span></p>
      <p v-if="hint" class="text-[0.85rem] text-courbe">{{ hint }}</p>
      <details class="mt-2">
        <summary class="cursor-pointer text-[0.9rem] text-courbe hover:text-papier">{{ t("field.see_list") }}</summary>
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
            <span class="text-[0.85rem] text-courbe">{{ t("field.english_name") }}</span>
            <input v-model="added.name" :class="input" placeholder="Laos" maxlength="60" />
          </label>
          <label class="w-20">
            <span class="text-[0.85rem] text-courbe">{{ t("field.code") }}</span>
            <input v-model="added.code" :class="input" placeholder="LA" maxlength="2" />
          </label>
          <button type="submit" class="rounded-md border border-foret/50 px-3 py-2 text-papier hover:bg-foret/10">{{ t("field.add") }}</button>
        </form>
      </details>
    </div>

    <!-- One value per category -->
    <div v-else-if="f.kind === 'categoryText' || f.kind === 'categoryNumber' || f.kind === 'categoryList'">
      <p>{{ label }}</p>
      <p v-if="hint" class="text-[0.85rem] text-courbe">{{ hint }}</p>
      <div class="mt-2 grid gap-2" :class="f.kind === 'categoryNumber' ? 'grid-cols-2' : 'grid-cols-1'">
        <label v-for="c in CATEGORIES" :key="c" class="block">
          <span class="text-[0.85rem] text-courbe">{{ categoryLabel(c) }}</span>
          <input :class="input" :value="categoryValue(c)" :inputmode="f.kind === 'categoryNumber' ? 'decimal' : 'text'"
                 @change="saveCategory(c, ($event.target as HTMLInputElement).value)" />
        </label>
      </div>
    </div>

    <!-- Simple fields -->
    <!-- The label on its own line: a narrow control (a number) never sits glued after it, hint or not. -->
    <label v-else class="block">
      <span class="block">{{ label }}</span>
      <span v-if="hint" class="block text-[0.85rem] text-courbe">{{ hint }}</span>
      <select v-if="f.kind === 'select'" :id="inputId" :class="input" :value="value" :disabled="disabled"
              @change="save(($event.target as HTMLSelectElement).value)">
        <option v-for="o in f.options" :key="o" :value="o">{{ optionLabel(f, o) }}</option>
      </select>
      <input v-else-if="f.kind === 'int' || f.kind === 'float'" :id="inputId" type="number" :class="[input, 'max-w-48']"
             :min="f.min" :max="f.max" :step="f.step ?? (f.kind === 'int' ? 1 : 'any')" :value="value" :disabled="disabled"
             @change="number(($event.target as HTMLInputElement).value)" />
      <input v-else-if="f.kind === 'rect'" :id="inputId" :class="input" :value="rectText(value)" :placeholder="t('field.whole_image')"
             :disabled="disabled" @change="saveRect(($event.target as HTMLInputElement).value)" />
      <textarea v-else-if="f.kind === 'rects'" :id="inputId" :class="input" rows="3" :value="(value as unknown[]).map(rectText).join('\n')"
                :disabled="disabled" spellcheck="false" @change="saveRects(($event.target as HTMLTextAreaElement).value)" />
      <textarea v-else-if="f.kind === 'textarea'" :id="inputId" :class="[input, 'font-mono text-[0.8rem]']" rows="10"
                :value="String(value ?? '')" :disabled="disabled" spellcheck="false"
                @change="save(($event.target as HTMLTextAreaElement).value)" />
      <input v-else :id="inputId" :class="input" :value="String(value ?? '')" :disabled="disabled" spellcheck="false"
             :list="f.section === 'vision' && f.key === 'model' ? 'nvidia-models' : undefined"
             @change="save(($event.target as HTMLInputElement).value.trim())" />
    </label>

    <p v-if="status" class="mt-1 text-[0.85rem]" :class="TONE[status.tone]" role="status">{{ status.text }}</p>
  </div>
</template>
