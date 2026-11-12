<script setup lang="ts">
// Marks: each clue circled on the frozen view, with its crop and what the AI read there word for word.
// They are pieces of evidence: the coach's conclusions will cite them by number.
import type { Evidence, Mark, Verdict } from "../engine";
import { engine, flag, num, removeMark, setLock } from "../engine";
import { quote, t, valueLabel } from "../i18n";

const props = defineProps<{ marks: Mark[]; analysisId: string; verdict: Verdict | null }>();

// What the local rules draw from a mark, in one line: "Благоевград → Blagoevgrad 🇧🇬".
const flags = (codes: string[]) => (codes.length > 6 ? t("marks.n_countries", { n: codes.length }) : codes.map(flag).join(" "));
const describe = (e: Evidence) =>
  e.kind === "alphabet" ? t("marks.colon", { label: e.label, value: flags(e.countries) }) : `${e.value} → ${e.label} ${flags(e.countries)}`;
/** What removes a proof from the computation, in plain words (empty: it counts). */
function status(n: number, e: Evidence): string {
  if (e.kind === "rue") return t("marks.street_name");
  if (e.note) return e.note;
  if (e.kind !== "lieu") return "";
  if (props.verdict?.ignored?.some((i) => i.n === n && i.value === e.value)) return t("marks.far_namesake");
  if (props.verdict?.unconfirmed?.some((u) => u.n === n && u.value === e.value)) {
    return t("marks.lone_place");
  }
  return "";
}
/** Place kept: the GeoNames name of the nearby namesake (Laàs in Béarn, not Laas in Gers). */
const placeLabel = (n: number, e: Evidence) =>
  props.verdict?.location?.places.find((p) => p.n === n && p.name === e.value)?.label ?? e.label;
function text(n: number, e: Evidence): string {
  if (e.kind === "rue") return e.value;
  if (e.kind === "lieu") return `${e.value} → ${placeLabel(n, e)} ${flags(e.countries)}`.trim();
  return describe(e);
}
/** City to lock from a place read: the namesake kept (the one on the map), otherwise the most populous. */
function cityOf(n: number, e: Evidence) {
  if (!engine.locks.enabled || e.kind !== "lieu" || status(n, e) || e.countries.length !== 1 || !e.points?.length) return null;
  const where = props.verdict?.location?.places.find((p) => p.n === n && p.name === e.value);
  const p = e.points.find((q) => q[2] === e.countries[0] && (!where || (Math.abs(q[0] - where.lat) < 1e-4 && Math.abs(q[1] - where.lon) < 1e-4)))
    ?? e.points.find((q) => q[2] === e.countries[0]);
  return p ? { level: "city" as const, country: p[2], name: p[3], lat: p[0], lon: p[1], region: p[4] ?? "" } : null;
}
const kind = (k: Evidence["kind"]) => t(`marks.kind.${k}`);
</script>

<template>
  <ol class="space-y-4">
    <li v-for="m in marks" :key="m.n" class="flex gap-3">
      <span class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-marque text-[0.9rem] font-bold text-encre">
        {{ m.n }}
      </span>
      <div class="min-w-0 flex-1 space-y-2">
        <img
          v-if="m.thumbnail"
          :src="m.thumbnail"
          :alt="t('marks.alt', { n: m.n })"
          class="max-h-40 max-w-full rounded border border-courbe-fonce"
        />
        <p v-if="m.status === 'pending'" class="flex items-center gap-2 text-courbe">
          <span class="inline-block size-2 animate-pulse rounded-full bg-lac motion-reduce:animate-none" aria-hidden="true" />
          {{ t("marks.reading") }}
        </p>
        <p v-else-if="m.status === 'error'" class="break-words text-[0.9rem] text-alerte" role="alert">
          {{ t("marks.read_failed", { error: m.error ?? "" }) }}
        </p>
        <template v-else>
          <p v-if="m.text.length" class="text-papier">
            <span v-for="(line, i) in m.text" :key="i" class="block">{{ quote(line) }}</span>
          </p>
          <p v-else-if="m.unreadable" class="text-papier">
            {{ t("marks.unreadable") }}
          </p>
          <p v-else class="text-courbe">{{ t("marks.no_text") }}</p>
          <ul v-if="m.evidence?.length" class="space-y-0.5 text-[0.85rem]" :aria-label="t('marks.proves_aria', { n: m.n })">
            <li v-for="(e, i) in m.evidence" :key="i" :title="e.source">
              <span :class="status(m.n, e) ? 'text-courbe' : 'text-marque'">{{ kind(e.kind) }}</span>{{ " " }}
              <span :class="status(m.n, e) ? 'text-courbe' : 'text-papier/90'">{{ text(m.n, e) }}</span>
              <span v-if="status(m.n, e)" class="text-courbe"> · {{ status(m.n, e) }}</span>
              <button
                v-if="cityOf(m.n, e)"
                type="button"
                class="ml-1.5 text-courbe underline underline-offset-2 hover:text-papier disabled:opacity-40"
                :title="t('marks.here_title', { city: cityOf(m.n, e)!.name })"
                :disabled="engine.busy"
                @click="setLock(analysisId, cityOf(m.n, e)!)"
              >
                {{ t("marks.here") }}
              </button>
            </li>
          </ul>
          <p v-if="m.scale >= 2.5" class="text-[0.85rem] text-courbe">
            {{ t("marks.small", { scale: num(m.scale) }) }}
          </p>
          <p class="text-[0.85rem] text-courbe">
            <button
              type="button"
              class="float-right ml-2 underline underline-offset-2 hover:text-papier"
              :title="t('marks.remove_title')"
              @click="removeMark(analysisId, m.n)"
            >
              {{ t("marks.remove") }}
            </button>
            {{ [m.object, m.script ? t("marks.alphabet", { script: valueLabel("script", m.script) }) : "", m.scale > 1 ? t("marks.enlarged", { scale: num(m.scale) }) : "", m.seconds !== undefined ? `${num(m.seconds)} s` : ""].filter(Boolean).join(" · ") }}
          </p>
        </template>
      </div>
    </li>
  </ol>
  <p class="mt-4 text-[0.85rem] text-courbe">
    {{ t("marks.footer") }} <kbd class="rounded border border-courbe-fonce px-1 text-papier">{{ t("key.super") }}</kbd>
    <kbd class="rounded border border-courbe-fonce px-1 text-papier">{{ t("key.shift") }}</kbd>
    <kbd class="rounded border border-courbe-fonce px-1 text-papier">Z</kbd>.
  </p>
</template>
