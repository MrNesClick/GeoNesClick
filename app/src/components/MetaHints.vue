<script setup lang="ts">
// The metas that tell the likely countries apart, with each one's own clue. Unverified clues from the seed
// are settled here ("Right" / "Wrong").
import type { LookFor } from "../engine";
import { countryName, engine, flag, judgeHint } from "../engine";
import { t } from "../i18n";

defineProps<{ lookfor: LookFor[] | null }>();
</script>

<template>
  <p v-if="!lookfor" class="text-courbe">{{ t("look.analysing") }}</p>
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
            <span v-if="h.source === 'mine'" class="text-[0.8rem] text-foret">
              {{ t(h.verified ? "metas.yours_verified" : "metas.yours") }}
            </span>
            <span v-else-if="!h.verified && h.seed && engine.metas.judge" class="inline-flex flex-wrap items-baseline gap-x-2 text-[0.8rem] text-courbe">
              {{ t("metas.seed") }}
              <button
                type="button"
                class="rounded px-1.5 text-foret underline underline-offset-2 hover:bg-foret/10 disabled:opacity-40"
                :disabled="engine.busy"
                :aria-label="t('metas.right_aria', { hint: h.hint })"
                @click="judgeHint(h.seed, 'right')"
              >{{ t("metas.right") }}</button>
              <button
                type="button"
                class="rounded px-1.5 text-alerte underline underline-offset-2 hover:bg-alerte/10 disabled:opacity-40"
                :disabled="engine.busy"
                :aria-label="t('metas.wrong_aria', { hint: h.hint })"
                @click="judgeHint(h.seed, 'wrong')"
              >{{ t("metas.wrong") }}</button>
            </span>
            <span v-else-if="!h.verified" class="text-[0.8rem] text-courbe">{{ t("metas.seed") }}</span>
          </span>
        </li>
      </ul>
    </div>
  </div>
  <p v-else class="text-[0.9rem] text-courbe">
    {{ t("metas.none") }}
  </p>
</template>
