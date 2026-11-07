<script setup lang="ts">
// Bandeau des verrous, en tête du coach (décidé avec l'utilisateur le 2026-11-07) : pays › région › ville fixés
// pour cette capture, par le coach (vert : règles locales) ou par toi (jaune : ta couleur sur les marques).
// - ✕ rejette un verrou pour toute la capture : le coach ne le reposera pas ;
// - « + » verrouille le niveau suivant, cherché dans l'index local (aucun réseau) ;
// - le nom d'un verrou du coach n'apparaît qu'au niveau d'aide qui le dévoile (pays au 3, le reste au 4) ;
//   en dessous, il est dit « caché », pour que tu saches que la recherche est restreinte ; les tiens restent visibles ;
// - les avis indépendants qui contredisent le pays verrouillé sont signalés : c'est ce qui révèle un verrou faux.
import { computed, nextTick, ref, watch } from "vue";
import type { Analysis, Lock, PlaceFound } from "../engine";
import { conclusionOf, countryName, engine, flag, normalise, rejectLock, searchPlaces, setLock } from "../engine";

const props = defineProps<{ analysis: Analysis }>();

const LEVELS = ["country", "region", "city"] as const;
type Level = (typeof LEVELS)[number];
const NOUN: Record<Level, string> = { country: "pays", region: "région", city: "ville" };
const level = computed(() => engine.helpLevel);
const held = computed(() => props.analysis.locks?.held ?? {});
const shown = (l: Lock) => l.by === "user" || level.value >= (l.level === "country" ? 3 : 4);
const label = (l: Lock) => (l.level === "country" ? `${flag(l.country)} ${countryName(l.country)}` : l.name);
const chips = computed(() => LEVELS.flatMap((lv) => (held.value[lv] ? [held.value[lv]!] : [])));
const proposal = computed(() => (level.value >= 4 ? props.analysis.locks?.proposal ?? null : null));
const rejected = computed(() => (props.analysis.locks?.rejected ?? []).filter(shown));

// Niveaux qu'on peut ajouter : le suivant, et la ville directement sous le pays. Jamais sous un verrou caché :
// les résultats de la recherche dévoileraient le pays.
const addable = computed<Level[]>(() => {
  const h = held.value;
  if (!h.country) return ["country"];
  if (!shown(h.country)) return [];
  if (!h.region) return h.city ? ["region"] : ["region", "city"];
  if (!shown(h.region) || h.city) return [];
  return ["city"];
});

// --- « + » : recherche ---------------------------------------------------------------------------
const adding = ref<Level | null>(null);
const query = ref("");
const results = ref<PlaceFound[]>([]);
const field = ref<HTMLInputElement | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;
let asked = 0;

async function open(lv: Level) {
  adding.value = lv;
  query.value = "";
  results.value = [];
  await nextTick();
  field.value?.focus();
  if (lv === "region") void find();
}
function close() {
  adding.value = null;
  clearTimeout(timer);
}
async function find() {
  const lv = adding.value;
  if (!lv) return;
  const q = query.value.trim();
  if (lv === "country") {
    const key = normalise(q);
    results.value = engine.countries
      .map((code) => ({ name: countryName(code), code }))
      .filter((c) => !key || normalise(c.name).split(/[\s-]+/).some((w) => w.startsWith(key)) || normalise(c.name).startsWith(key))
      .sort((a, b) => a.name.localeCompare(b.name, "fr"))
      .slice(0, 12);
    return;
  }
  const country = held.value.country!.country;
  const ticket = ++asked; // une réponse lente ne doit pas remplacer une plus récente
  const found = await searchPlaces(lv, q, country, lv === "city" ? held.value.region?.region ?? "" : "");
  if (ticket === asked) results.value = found;
}
watch(query, () => {
  clearTimeout(timer);
  timer = setTimeout(find, adding.value === "country" ? 0 : 200);
});
async function choose(r: PlaceFound) {
  const lv = adding.value;
  if (!lv) return;
  const id = props.analysis.id;
  if (lv === "country") await setLock(id, { level: "country", country: r.code! });
  else if (lv === "region") await setLock(id, { level: "region", country: held.value.country!.country, region: r.code });
  else await setLock(id, { level: "city", country: r.country!, region: r.region, name: r.name, lat: r.lat, lon: r.lon });
  close();
}
const resultLabel = (r: PlaceFound) =>
  adding.value === "country" ? `${flag(r.code!)} ${r.name}`
    : adding.value === "city" && r.region_name && !held.value.region ? `${r.name} · ${r.region_name}` : r.name;

// --- désaccords : avis indépendants contre le pays verrouillé ---------------------------------------
const pct = (p: number) => `${Math.round(p * 100)} %`;
const disagreements = computed(() => {
  const c = held.value.country;
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
  const outside = props.analysis.marks.flatMap((m) => m.evidence ?? []).filter((e) => e.note?.includes("verrouill")).length;
  if (outside) out.push(`${outside} preuve${outside > 1 ? "s" : ""} de tes marques hors du verrou : vois « Marques ».`);
  return out;
});

const reject = (lv: Level | "proposal") => rejectLock(props.analysis.id, lv);
const accept = (p: Lock) => setLock(props.analysis.id, p);
</script>

<template>
  <section aria-labelledby="verrous-titre" class="mt-3 rounded-md border border-courbe-fonce px-3 py-2">
    <div class="flex flex-wrap items-center gap-x-1.5 gap-y-1.5">
      <h2 id="verrous-titre" class="mr-1 text-[0.85rem] font-bold text-courbe">Verrous</h2>
      <template v-for="(l, i) in chips" :key="l.level">
        <span v-if="i" class="text-courbe" aria-hidden="true">›</span>
        <span
          class="inline-flex items-center gap-1.5 rounded border py-0.5 pr-1 pl-2 text-[0.9rem]"
          :class="l.by === 'user' ? 'border-marque/70' : 'border-foret/70'"
          :title="l.by === 'coach' ? `Verrouillé par le coach : ${l.why}` : 'Verrouillé par toi'"
        >
          <span v-if="shown(l)" class="text-papier">{{ label(l) }}</span>
          <span v-else class="text-courbe">{{ NOUN[l.level] }} verrouillé{{ l.level === "region" || l.level === "city" ? "e" : "" }}, caché à ce niveau</span>
          <span class="text-[0.8rem]" :class="l.by === 'user' ? 'text-marque' : 'text-foret'">{{ l.by === "user" ? "toi" : "coach" }}</span>
          <button
            type="button"
            class="rounded px-1 text-courbe hover:bg-alerte/15 hover:text-papier disabled:opacity-40"
            :aria-label="`Rejeter le verrou ${NOUN[l.level]}${shown(l) ? ` ${label(l)}` : ''}`"
            :title="l.by === 'coach' ? 'Pas ça : le coach ne le reverrouillera pas pendant cette capture.' : 'Pas ça : retiré (avec les niveaux du dessous) pour toute la capture ; le coach ne le reposera pas.'"
            :disabled="engine.busy"
            @click="reject(l.level)"
          >
            ✕
          </button>
        </span>
      </template>
      <span v-if="chips.length && addable.length" class="text-courbe" aria-hidden="true">›</span>
      <button
        v-for="lv in addable"
        :key="lv"
        type="button"
        class="rounded border border-dashed border-courbe-fonce px-2 py-0.5 text-[0.9rem] text-courbe hover:border-courbe hover:text-papier"
        :aria-expanded="adding === lv"
        @click="adding === lv ? close() : open(lv)"
      >
        + {{ NOUN[lv] }}
      </button>
      <span v-if="!chips.length && !adding" class="text-[0.85rem] text-courbe">rien de fixé pour l'instant</span>
    </div>

    <!-- « + » : recherche dans l'index local -->
    <div v-if="adding" class="mt-2">
      <label :for="`verrou-${adding}`" class="sr-only">Chercher {{ NOUN[adding] === "pays" ? "un pays" : `une ${NOUN[adding]}` }}</label>
      <input
        :id="`verrou-${adding}`"
        ref="field"
        v-model="query"
        type="search"
        autocomplete="off"
        class="w-full rounded border border-courbe-fonce bg-relief px-2 py-1 text-papier placeholder:text-courbe"
        :placeholder="adding === 'country' ? 'Pays…' : adding === 'region' ? 'Région…' : 'Ville ou village (2 lettres au moins)…'"
        @keydown.escape="close"
        @keydown.enter.prevent="results[0] && choose(results[0])"
      />
      <ul v-if="results.length" class="mt-1 max-h-48 overflow-y-auto" :aria-label="`Résultats : ${NOUN[adding]}`">
        <li v-for="r in results" :key="`${r.code ?? ''}${r.name}${r.lat ?? ''}`">
          <button type="button" class="w-full rounded px-2 py-1 text-left text-papier hover:bg-relief" @click="choose(r)">
            {{ resultLabel(r) }}
          </button>
        </li>
      </ul>
      <p v-else-if="adding !== 'country' && !engine.places.ready" class="mt-1 text-[0.85rem] text-courbe">
        Répertoire des lieux indisponible : {{ engine.places.message }}
      </p>
      <p v-else-if="query.trim().length >= 2" class="mt-1 text-[0.85rem] text-courbe">Aucun résultat.</p>
    </div>

    <!-- Ville proposée par le coach : jamais verrouillée sans toi -->
    <p v-if="proposal" class="mt-2 flex flex-wrap items-center gap-2 text-[0.9rem]">
      <span class="text-papier">{{ proposal.name }} ?</span>
      <span class="text-[0.85rem] text-courbe">{{ proposal.why }}</span>
      <button type="button" class="rounded border border-foret/70 px-2 py-0.5 text-papier hover:bg-foret/10 disabled:opacity-40"
              :disabled="engine.busy" @click="accept(proposal)">
        Verrouiller
      </button>
      <button type="button" class="rounded px-1 text-courbe hover:text-papier disabled:opacity-40" :disabled="engine.busy"
              :aria-label="`Pas ${proposal.name}`" @click="reject('proposal')">
        ✕
      </button>
    </p>

    <p v-for="d in disagreements" :key="d" class="mt-1.5 border-l-2 border-alerte/70 pl-2 text-[0.85rem] text-papier">
      {{ d }} Si le verrou est faux, rejette-le (✕).
    </p>
    <p v-if="rejected.length" class="mt-1.5 text-[0.85rem] text-courbe">
      Rejeté pour cette capture : {{ rejected.map(label).join(", ") }}.
    </p>
  </section>
</template>
