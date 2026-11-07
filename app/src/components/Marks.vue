<script setup lang="ts">
// Marques : chaque indice entouré sur la vue figée, avec sa découpe et ce que l'IA y a lu mot pour mot.
// Ce sont des éléments de preuve : les conclusions du coach les citeront par leur numéro.
import type { Evidence, Mark, Verdict } from "../engine";
import { flag, fr, removeMark } from "../engine";

const props = defineProps<{ marks: Mark[]; analysisId: string; verdict: Verdict | null }>();

// Ce que les règles locales tirent d'une marque, en une ligne : « Благоевград → Blagoevgrad 🇧🇬 ».
const flags = (codes: string[]) => (codes.length > 6 ? `${codes.length} pays` : codes.map(flag).join(" "));
const describe = (e: Evidence) =>
  e.kind === "alphabet" ? `${e.label} : ${flags(e.countries)}` : `${e.value} → ${e.label} ${flags(e.countries)}`;
/** Ce qui retire une preuve du calcul, dit en clair (vide : elle compte). */
function status(n: number, e: Evidence): string {
  if (e.kind === "rue") return "nom de rue, ne situe pas la vue";
  if (e.note) return e.note;
  if (e.kind !== "lieu") return "";
  if (props.verdict?.ignored?.some((i) => i.n === n && i.value === e.value)) return "homonyme lointain, ignoré";
  if (props.verdict?.unconfirmed?.some((u) => u.n === n && u.value === e.value)) {
    return "indice seul : un lieu ne conclut qu'avec une autre preuve";
  }
  return "";
}
/** Lieu retenu : le nom GeoNames de l'homonyme voisin (Laàs du Béarn, pas Laas du Gers). */
const placeLabel = (n: number, e: Evidence) =>
  props.verdict?.location?.places.find((p) => p.n === n && p.name === e.value)?.label ?? e.label;
function text(n: number, e: Evidence): string {
  if (e.kind === "rue") return e.value;
  if (e.kind === "lieu") return `${e.value} → ${placeLabel(n, e)} ${flags(e.countries)}`.trim();
  return describe(e);
}
const KIND: Record<Evidence["kind"], string> = {
  alphabet: "Alphabet", lettres: "Lettres", mot: "Mot", lieu: "Lieu", rue: "Rue",
};
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
          :alt="`Marque ${m.n}`"
          class="max-h-40 max-w-full rounded border border-courbe-fonce"
        />
        <p v-if="m.status === 'pending'" class="flex items-center gap-2 text-courbe">
          <span class="inline-block size-2 animate-pulse rounded-full bg-lac motion-reduce:animate-none" aria-hidden="true" />
          Lecture en cours…
        </p>
        <p v-else-if="m.status === 'error'" class="break-words text-[0.9rem] text-alerte" role="alert">
          Lecture impossible : {{ m.error }}
        </p>
        <template v-else>
          <p v-if="m.text.length" class="text-papier">
            <span v-for="(line, i) in m.text" :key="i" class="block">« {{ line }} »</span>
          </p>
          <p v-else-if="m.unreadable" class="text-papier">
            Texte illisible : entoure-le de plus près, ou zoome dans le jeu puis marque à nouveau.
          </p>
          <p v-else class="text-courbe">Aucun texte.</p>
          <ul v-if="m.evidence?.length" class="space-y-0.5 text-[0.85rem]" :aria-label="`Ce que la marque ${m.n} prouve`">
            <li v-for="(e, i) in m.evidence" :key="i" :title="e.source">
              <span :class="status(m.n, e) ? 'text-courbe' : 'text-marque'">{{ KIND[e.kind] }}</span>{{ " " }}
              <span :class="status(m.n, e) ? 'text-courbe' : 'text-papier/90'">{{ text(m.n, e) }}</span>
              <span v-if="status(m.n, e)" class="text-courbe"> · {{ status(m.n, e) }}</span>
            </li>
          </ul>
          <p v-if="m.scale >= 2.5" class="text-[0.85rem] text-courbe">
            Petite à l'origine (agrandie ×{{ fr(m.scale) }}) : l'agrandissement n'invente pas les détails. Si un texte
            manque, zoome dessus dans le jeu puis marque-le de près.
          </p>
          <p class="text-[0.85rem] text-courbe">
            <button
              type="button"
              class="float-right ml-2 underline underline-offset-2 hover:text-papier"
              :title="'Lecture fausse ou découpe ratée : la marque ne comptera plus dans la réponse.'"
              @click="removeMark(analysisId, m.n)"
            >
              Retirer
            </button>
            {{ [m.object, m.script && m.script !== "aucun" ? `alphabet ${m.script}` : "", m.scale > 1 ? `agrandie ×${fr(m.scale)}` : "", m.seconds !== undefined ? `${fr(m.seconds)} s` : ""].filter(Boolean).join(" · ") }}
          </p>
        </template>
      </div>
    </li>
  </ol>
  <p class="mt-4 text-[0.85rem] text-courbe">
    Lu par l'IA, mot pour mot ; conclu par les règles du coach (noms de lieux : GeoNames, CC BY 4.0). Ajoute des marques avec <kbd class="rounded border border-courbe-fonce px-1 text-papier">Super</kbd>
    <kbd class="rounded border border-courbe-fonce px-1 text-papier">Maj</kbd>
    <kbd class="rounded border border-courbe-fonce px-1 text-papier">Z</kbd>.
  </p>
</template>
