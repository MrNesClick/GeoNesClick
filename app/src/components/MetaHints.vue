<script setup lang="ts">
// Les metas qui départagent les pays probables, avec l'indice propre à chacun. Les indices de l'amorce
// non vérifiés se tranchent ici (« Juste » / « Faux »).
import type { LookFor } from "../engine";
import { countryName, engine, flag, judgeHint } from "../engine";

defineProps<{ lookfor: LookFor[] | null }>();
</script>

<template>
  <p v-if="!lookfor" class="text-courbe">Analyse de la vue en cours…</p>
  <div v-else-if="lookfor.length" class="space-y-4">
    <div v-for="lf in lookfor" :key="lf.category">
      <h3 class="text-[0.9rem] font-bold text-foret">{{ lf.label }}</h3>
      <ul class="mt-1.5 space-y-1.5">
        <li v-for="h in lf.hints" :key="h.hint" class="flex gap-2.5 text-[0.95rem]">
          <span class="shrink-0 tracking-wider" :title="h.countries.map(countryName).join(', ')">
            <span v-for="c in h.countries" :key="c" aria-hidden="true">{{ flag(c) }}</span>
            <span class="sr-only">{{ h.countries.map(countryName).join(", ") }}</span>
          </span>
          <span class="text-papier">
            {{ h.hint }}
            <span v-if="h.source === 'mes metas'" class="text-[0.8rem] text-foret">
              {{ h.verified ? "(ta meta, vérifiée)" : "(ta meta)" }}
            </span>
            <span v-else-if="!h.verified && engine.metas.judge" class="inline-flex flex-wrap items-baseline gap-x-2 text-[0.8rem] text-courbe">
              (amorce, à vérifier)
              <button
                type="button"
                class="rounded px-1.5 text-foret underline underline-offset-2 hover:bg-foret/10 disabled:opacity-40"
                :disabled="engine.busy"
                :aria-label="`Juste : ${h.hint}`"
                @click="judgeHint(lf.category, h.hint, 'right')"
              >Juste</button>
              <button
                type="button"
                class="rounded px-1.5 text-alerte underline underline-offset-2 hover:bg-alerte/10 disabled:opacity-40"
                :disabled="engine.busy"
                :aria-label="`Faux : ${h.hint}`"
                @click="judgeHint(lf.category, h.hint, 'wrong')"
              >Faux</button>
            </span>
            <span v-else-if="!h.verified" class="text-[0.8rem] text-courbe">(amorce, à vérifier)</span>
          </span>
        </li>
      </ul>
    </div>
  </div>
  <p v-else class="text-[0.9rem] text-courbe">
    Aucune meta ne départage ces pays. Ajoute les tiennes dans ~/.config/geonesclick/mes-metas.toml.
  </p>
</template>
