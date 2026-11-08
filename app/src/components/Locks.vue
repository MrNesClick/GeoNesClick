<script setup lang="ts">
// "Do you know where you are? Tell the coach": the country › region › city locks, at the top of the coach (decided
// with the user on 2026-11-07; "sentence + list" version chosen the same evening, the word "lock" was not clear).
// - Nothing certain: a sentence and the list of countries (StreetCLIP candidates first, from level 3; at levels 1
//   and 2 it only opens on click, without percentages, so as to reveal nothing).
// - Chosen: "C'est sûr : 🇨🇿 Tchéquie (toi) ✕", then Region and City to choose the same way (local index).
// - ✕ = "not that" for the whole capture: the coach will not set it again.
// - What the coach set on its own is named only at the help level that reveals it (country at 3, the rest at 4);
//   below that: "the coach is sure of it (hidden at this help level)".
// - Independent opinions that contradict the chosen country are flagged: that is what reveals a mistake.
import { computed, nextTick, ref, watch } from "vue";
import type { Analysis, Lock, PlaceFound } from "../engine";
import { circled, conclusionOf, countryName, engine, flag, normalise, rejectLock, removeMark, searchPlaces, setLock } from "../engine";

const props = defineProps<{ analysis: Analysis }>();

type Level = "country" | "region" | "city";
const NOUN: Record<Level, string> = { country: "Pays", region: "Région", city: "Ville" };
const level = computed(() => engine.helpLevel);
const held = computed(() => props.analysis.locks?.held ?? {});
const shown = (l: Lock) => l.by === "user" || level.value >= (l.level === "country" ? 3 : 4);
const label = (l: Lock) => (l.level === "country" ? `${flag(l.country)} ${countryName(l.country)}` : l.name);
const proposal = computed(() => (level.value >= 4 ? props.analysis.locks?.proposal ?? null : null));
const rejected = computed(() => (props.analysis.locks?.rejected ?? []).filter(shown));
// Regions of the places read (except those you ruled out): one click to choose, especially when they disagree.
const readRegions = computed(() => (props.analysis.locks?.read_regions ?? [])
  .filter((r) => !props.analysis.locks?.rejected.some((x) => x.level === "region" && x.region === r.code)));
const sure = computed(() => [held.value.country, held.value.region, held.value.city].filter((x): x is Lock => !!x));
const pct = (p: number) => `${Math.round(p * 100)} %`;

// Rows to choose under the country: never under a hidden choice (the results would reveal the country).
const country = computed(() => held.value.country ?? null);
const pickable = computed<Level[]>(() => {
  const c = country.value;
  if (!c || !shown(c)) return [];
  const out: Level[] = [];
  if (!held.value.region && !held.value.city) out.push("region");
  if (!held.value.city && !proposal.value && (!held.value.region || shown(held.value.region))) out.push("city");
  return out;
});

// --- choosing a place -------------------------------------------------------------------------
const active = ref<Level | null>(null);
const query = ref("");
const found = ref<PlaceFound[]>([]);
const fields: Partial<Record<Level, HTMLInputElement | null>> = {};
let timer: ReturnType<typeof setTimeout> | undefined;
let asked = 0;

/** Countries offered: StreetCLIP's first (with their %, from level 3), then the others. */
const countries = computed(() => {
  const key = normalise(query.value);
  const scores = level.value >= 3 ? props.analysis.scores ?? [] : [];
  const pctOf = (code: string) => scores.find((s) => s.code === code)?.probability;
  const match = (name: string) => !key || normalise(name).startsWith(key) ||
    normalise(name).split(/[\s-]+/).some((w) => w.startsWith(key));
  return engine.countries
    .map((code) => ({ code, name: countryName(code), p: pctOf(code) }))
    .filter((c) => match(c.name))
    .sort((a, b) => (b.p ?? -1) - (a.p ?? -1) || a.name.localeCompare(b.name, "fr"));
});
// Without a click, from level 3: the 3 most likely countries, ready to be chosen.
const quick = computed(() => (level.value >= 3 && active.value !== "country"
  ? countries.value.filter((c) => c.p !== undefined).slice(0, 3) : []));

async function open(lv: Level) {
  if (active.value !== lv) {
    active.value = lv;
    query.value = "";
    found.value = [];
    if (lv === "region") void find();
  }
  await nextTick();
  fields[lv]?.focus();
}
function close() {
  active.value = null;
  query.value = "";
  clearTimeout(timer);
}
async function find() {
  const lv = active.value;
  if (!lv || lv === "country" || !country.value) return;
  const ticket = ++asked; // a slow response does not replace a more recent one
  const res = await searchPlaces(lv, query.value.trim(), country.value.country,
                                 lv === "city" ? held.value.region?.region ?? "" : "");
  if (ticket === asked) found.value = res;
}
function typed(lv: Level, value: string) {
  if (active.value !== lv) void open(lv);
  query.value = value;
  clearTimeout(timer);
  if (lv !== "country") timer = setTimeout(find, 200);
}
async function chooseCountry(code: string) {
  await setLock(props.analysis.id, { level: "country", country: code });
  close();
}
async function choosePlace(r: PlaceFound) {
  const c = country.value;
  if (!c) return;
  if (active.value === "region") await setLock(props.analysis.id, { level: "region", country: c.country, region: r.code });
  else await setLock(props.analysis.id, { level: "city", country: r.country!, region: r.region, name: r.name, lat: r.lat, lon: r.lon });
  close();
}
function enter(lv: Level) {
  if (lv === "country") {
    if (countries.value[0]) void chooseCountry(countries.value[0].code);
  } else if (found.value[0]) void choosePlace(found.value[0]);
}
watch(() => props.analysis.id, close); // new capture: no list left open from the previous one
const placeLabel = (r: PlaceFound) => (r.region_name && !held.value.region ? `${r.name} · ${r.region_name}` : r.name);

// --- disagreements: independent opinions against the chosen country -----------------------------------
const disagreements = computed(() => {
  const c = country.value;
  if (!c || level.value < 3) return [];
  const out: string[] = [];
  const scores = props.analysis.scores ?? [];
  const top = scores[0];
  const mine = scores.find((s) => s.code === c.country);
  if (top && top.code !== c.country && top.probability - (mine?.probability ?? 0) >= engine.leader.margin) {
    out.push(`StreetCLIP voit plutôt ${flag(top.code)} ${countryName(top.code)} (${pct(top.probability)}` +
      `${mine ? `, ${countryName(c.country)} ${pct(mine.probability)}` : ""}).`);
  }
  const vision = props.analysis.vision.status === "done" ? conclusionOf(props.analysis.vision.fiche) : null;
  if (vision && vision.country !== c.country) {
    out.push(`L'IA a lu une preuve pour ${flag(vision.country)} ${countryName(vision.country)}` +
      `${vision.proof ? ` (« ${vision.proof} »)` : ""}.`);
  }
  return out;
});

// What your marks conclude WITHOUT taking your choice into account (engine): they confirm or contradict it.
// STRONG contradiction (another "certain" country, or an alphabet that excludes your country): alert at the top and
// two one-click ways out, since the mistake may come from your choice OR from a misreading ("PALERMO" read
// "PILIERNO"); the coach never replaces your choice itself (decided with the user on 2026-11-07). Weak ("very
// likely"): one line.
interface MarksSay { kind: "ok" | "weak" | "strong"; text: string; other: string | null; marks: number[] }
const marksSay = computed<MarksSay | null>(() => {
  const c = country.value;
  const v = props.analysis.verdict;
  if (!c || c.by !== "user" || !v) return null; // a country set by the coach already comes from your marks
  const cites = v.cites.map((x) => `${circled(x.n)} ${x.items.join(", ")}`).join(" · ");
  if (v.country === c.country && v.level) {
    return { kind: "ok", other: null, marks: [],
             text: `${v.level === "certain" ? "tes marques le confirment" : "tes marques vont dans ce sens (très probable)"} : ${cites}` };
  }
  if (v.country && v.country !== c.country) {
    const strong = v.level === "certain";
    const named = level.value >= 3 ? `${flag(v.country)} ${countryName(v.country)}${strong ? ", certain" : ", très probable"} : ${cites}`
      : "un autre pays (niveau 3 pour voir lequel)";
    return { kind: strong ? "strong" : "weak", text: named, other: level.value >= 3 ? v.country : null,
             marks: v.cites.map((x) => x.n) };
  }
  if (v.allowed && !v.allowed.includes(c.country)) { // a mark's alphabet excludes your country
    const marks = props.analysis.marks
      .filter((m) => m.evidence?.some((e) => e.kind === "alphabet" && !e.countries.includes(c.country))).map((m) => m.n);
    return { kind: "strong", other: null, marks,
             text: `l'alphabet ${v.scripts.join(", ")} (${marks.map(circled).join(" ")}) ne s'écrit pas dans ce pays` };
  }
  return null;
});
const switchTo = (code: string) => setLock(props.analysis.id, { level: "country", country: code });

const reject = (lv: Level | "proposal") => rejectLock(props.analysis.id, lv);
const by = (l: Lock) => (l.by === "user" ? "toi" : "le coach");
const input = "w-full rounded border border-courbe-fonce bg-relief px-2 py-1 text-papier placeholder:text-courbe";
const option = "flex w-full items-center justify-between gap-3 rounded px-2 py-1 text-left text-papier hover:bg-relief disabled:opacity-40";
</script>

<template>
  <section aria-label="Ce qui est sûr" class="mt-3 rounded-md border border-courbe-fonce px-3 py-2 text-[0.9rem]">
    <!-- Nothing certain: the sentence, the field and the likely countries -->
    <template v-if="!country">
      <p class="text-papier">Tu sais où tu es ? Dis-le au coach :</p>
      <div class="mt-1.5 flex items-center gap-2">
        <label for="sur-country" class="w-16 shrink-0 text-courbe">Pays</label>
        <input id="sur-country" :ref="(el) => (fields.country = el as HTMLInputElement | null)"
               :value="active === 'country' ? query : ''" type="search" autocomplete="off" :class="input"
               placeholder="choisis ou tape un nom…"
               @focus="open('country')" @input="typed('country', ($event.target as HTMLInputElement).value)"
               @keydown.escape="close" @keydown.enter.prevent="enter('country')" />
      </div>
      <ul v-if="active === 'country' || quick.length" class="mt-1 ml-[4.5rem] max-h-56 overflow-y-auto" aria-label="Pays">
        <li v-for="c in active === 'country' ? countries : quick" :key="c.code">
          <button type="button" :class="option" :disabled="engine.busy" @click="chooseCountry(c.code)">
            <span>{{ flag(c.code) }} {{ c.name }}</span>
            <span v-if="c.p !== undefined" class="tabular-nums text-courbe">{{ pct(c.p) }}</span>
          </button>
        </li>
        <li v-if="active !== 'country'" class="px-2 text-[0.85rem] text-courbe">… ou tape pour chercher un autre pays</li>
      </ul>
    </template>

    <!-- What is certain, level by level -->
    <template v-else>
      <p v-for="l in sure" :key="l.level" class="flex flex-wrap items-center gap-x-2"
         :class="l.level === 'country' ? '' : 'mt-1 ml-4'">
        <span class="text-courbe">{{ l.level === "country" ? "C'est sûr :" : `› ${NOUN[l.level]} :` }}</span>
        <span v-if="shown(l)" class="text-papier">{{ label(l) }}</span>
        <span v-else class="text-courbe">le coach en est sûr (caché à ce niveau d'aide)</span>
        <span class="text-[0.85rem]" :class="l.by === 'user' ? 'text-marque' : 'text-foret'"
              :title="l.by === 'coach' ? `D'après ${l.why}` : ''">({{ by(l) }})</span>
        <button type="button" class="rounded px-1.5 text-courbe hover:bg-alerte/15 hover:text-papier disabled:opacity-40"
                :aria-label="`Pas ça : ${shown(l) ? label(l) : NOUN[l.level].toLowerCase()}`"
                title="Pas ça : retiré pour toute cette capture, le coach ne le reproposera pas."
                :disabled="engine.busy" @click="reject(l.level)">
          ✕
        </button>
      </p>

      <p v-if="marksSay?.kind === 'ok'" class="mt-1 ml-4 text-[0.85rem] text-foret">✓ {{ marksSay.text }}</p>
      <p v-else-if="marksSay?.kind === 'weak'" class="mt-1 ml-4 border-l-2 border-alerte/50 pl-2 text-[0.85rem] text-courbe">
        Tes marques penchent pour {{ marksSay.text }}.
      </p>
      <div v-else-if="marksSay" class="mt-2 rounded border border-alerte/70 bg-alerte/10 px-2.5 py-2" role="alert">
        <p class="font-bold text-papier">⚠ Tes marques prouvent autre chose</p>
        <p class="mt-0.5 text-papier">{{ marksSay.text }}.</p>
        <p class="mt-0.5 text-[0.85rem] text-courbe">Soit ton choix est faux, soit une marque est mal lue :</p>
        <div class="mt-1.5 flex flex-wrap gap-2">
          <button v-if="marksSay.other" type="button" :disabled="engine.busy"
                  class="rounded border border-papier/60 px-2 py-0.5 text-papier hover:bg-papier/10 disabled:opacity-40"
                  @click="switchTo(marksSay.other)">
            Passer à {{ flag(marksSay.other) }} {{ countryName(marksSay.other) }}
          </button>
          <button v-for="n in marksSay.marks" :key="n" type="button" :disabled="engine.busy"
                  class="rounded border border-courbe-fonce px-2 py-0.5 text-papier hover:bg-relief disabled:opacity-40"
                  :title="`La lecture de la marque ${n} est fausse : elle ne comptera plus.`"
                  @click="removeMark(analysis.id, n)">
            {{ circled(n) }} est mal lue : la retirer
          </button>
        </div>
      </div>

      <!-- City suggested by the coach (never chosen without you) -->
      <p v-if="proposal" class="mt-1 ml-4 flex flex-wrap items-center gap-2">
        <span class="text-courbe">› Ville :</span>
        <span class="text-papier">{{ proposal.name }} ?</span>
        <button type="button" class="rounded border border-foret/70 px-2 text-papier hover:bg-foret/10 disabled:opacity-40"
                :disabled="engine.busy" :title="`Le coach le propose : ${proposal.why}`" @click="setLock(analysis.id, proposal)">
          Oui
        </button>
        <button type="button" class="rounded px-1.5 text-courbe hover:text-papier disabled:opacity-40" :disabled="engine.busy"
                :aria-label="`Pas ${proposal.name}`" @click="reject('proposal')">
          ✕
        </button>
      </p>

      <!-- Region and city: to choose, searched in the local index -->
      <div v-for="lv in pickable" :key="lv" class="mt-1 ml-4">
        <div v-if="lv === 'region' && readRegions.length" class="mb-1 flex flex-wrap items-center gap-1.5">
          <span class="w-16 shrink-0 text-courbe">› Région</span>
          <span class="text-[0.85rem] text-courbe">
            {{ readRegions.length > 1 ? `tes marques citent ${readRegions.length} régions :` : "tes marques citent :" }}
          </span>
          <button v-for="r in readRegions" :key="r.code" type="button" :disabled="engine.busy"
                  class="rounded border border-courbe-fonce px-2 py-0.5 text-papier hover:border-marque/70 disabled:opacity-40"
                  :title="`Choisir ${r.name}`"
                  @click="setLock(analysis.id, { level: 'region', country: country!.country, region: r.code })">
            {{ r.name }} <span class="text-courbe">{{ r.marks.map(circled).join(" ") }} {{ r.places.join(", ") }}</span>
          </button>
        </div>
        <div class="flex items-center gap-2">
          <label :for="`sur-${lv}`" class="w-16 shrink-0 text-courbe">{{ lv === "region" && readRegions.length ? "ou" : `› ${NOUN[lv]}` }}</label>
          <input :id="`sur-${lv}`" :ref="(el) => (fields[lv] = el as HTMLInputElement | null)"
                 :value="active === lv ? query : ''" type="search" autocomplete="off" :class="input"
                 :placeholder="lv === 'region' ? 'choisis dans la liste…' : 'tape le nom (2 lettres au moins)…'"
                 @focus="open(lv)" @input="typed(lv, ($event.target as HTMLInputElement).value)"
                 @keydown.escape="close" @keydown.enter.prevent="enter(lv)" />
        </div>
        <template v-if="active === lv">
          <ul v-if="found.length" class="mt-1 ml-[4.5rem] max-h-48 overflow-y-auto" :aria-label="NOUN[lv]">
            <li v-for="r in found" :key="`${r.code ?? ''}${r.name}${r.lat ?? ''}`">
              <button type="button" :class="option" :disabled="engine.busy" @click="choosePlace(r)">{{ placeLabel(r) }}</button>
            </li>
          </ul>
          <p v-else-if="!engine.places.ready" class="mt-1 ml-[4.5rem] text-[0.85rem] text-courbe">
            Répertoire des lieux indisponible : {{ engine.places.message }}
          </p>
          <p v-else-if="query.trim().length >= 2" class="mt-1 ml-[4.5rem] text-[0.85rem] text-courbe">Aucun résultat.</p>
        </template>
      </div>

      <p v-for="d in disagreements" :key="d" class="mt-1.5 border-l-2 border-alerte/70 pl-2 text-[0.85rem] text-papier">
        {{ d }} Si le pays est faux, clique ✕.
      </p>
    </template>

    <p v-if="rejected.length" class="mt-1.5 text-[0.85rem] text-courbe">
      Pas ça (pour cette capture) : {{ rejected.map(label).join(", ") }}.
    </p>
  </section>
</template>
