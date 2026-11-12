<script setup lang="ts">
// Settings screen: EVERYTHING is configurable. Seven collapsible groups in the coach's format (title + one-line
// summary), described in settingsSchema.ts; fine-grained settings are under "Advanced". Each change applies and
// is saved right away. File-only settings (security) are shown read-only, with their reason and where to
// change them.
import { onMounted, reactive, ref } from "vue";
import type { FileOnly, Settings } from "../engine";
import { engine, num, getJSON, refreshPlonkit, reselectWindow, saveApiKey, saveSetting, testModel } from "../engine";
import type { Field, Group } from "../settingsSchema";
import { fileOnlyLabel, GROUPS, groupTitle, optionLabel } from "../settingsSchema";
import { t } from "../i18n";
import Section from "./Section.vue";
import SettingField from "./SettingField.vue";
import StoragePanel from "./StoragePanel.vue";

const s = ref<Settings | null>(null);
const fileOnly = ref<FileOnly | null>(null);
const models = ref<string[]>([]);
const test = ref<{ model: string; text: string; ok: boolean } | null>(null);
const testing = ref(false);
/** Saving state of each setting ("section.key"). */
const status = reactive<Record<string, { tone: "ok" | "error" | "busy"; text: string }>>({});
const timers: Record<string, ReturnType<typeof setTimeout>> = {};

async function load() {
  [s.value, fileOnly.value] = await Promise.all([getJSON<Settings>("/settings"), getJSON<FileOnly>("/settings/file-only")]);
}
onMounted(async () => {
  await load();
  models.value = (await getJSON<{ models: string[] }>("/models"))?.models ?? [];
});

const fieldId = (f: Field) => `${f.section}.${f.key}`;

async function save(f: Field, section: string, key: string, value: unknown) {
  const id = fieldId(f);
  clearTimeout(timers[id]);
  status[id] = { tone: "busy", text: t("settings.saving") };
  const r = await saveSetting(section, key, value);
  if (r.error) {
    status[id] = { tone: "error", text: r.error };
    await load(); // the screen goes back to the value actually in effect
    return;
  }
  if (s.value) s.value[section][key] = value;
  status[id] = { tone: "ok", text: t(r.restart ? "settings.saved_restart" : "settings.saved") };
  if (!r.restart) timers[id] = setTimeout(() => delete status[id], 2500);
}
const invalid = (f: Field, text: string) => (status[fieldId(f)] = { tone: "error", text });

// NVIDIA API key: entered here, stored by the engine in ~/.config/geonesclick/nvapi.key (readable by you only).
const keyInput = ref("");
const keyStatus = ref<{ tone: "ok" | "error"; text: string } | null>(null);
async function storeKey(value: string) {
  if (value && !value.trim().startsWith("nvapi-")) {
    keyStatus.value = { tone: "error", text: t("settings.key_prefix") };
    return;
  }
  const error = await saveApiKey(value);
  keyStatus.value = error ? { tone: "error", text: error } : { tone: "ok", text: t(value ? "settings.key_saved" : "settings.key_forgotten") };
  if (!error) keyInput.value = "";
  models.value = (await getJSON<{ models: string[] }>("/models"))?.models ?? [];
}

async function runTest() {
  const model = String(s.value?.vision.model ?? "");
  testing.value = true;
  const r = await testModel(model);
  testing.value = false;
  test.value = r.ok
    ? { model, ok: true, text: t("settings.model_ok", { s: num(r.seconds ?? 0) }) }
    : { model, ok: false, text: r.error ?? t("settings.model_failed") };
}

// --- One-line summaries, readable when the section is collapsed ---------------------------------------
const languageField = GROUPS.flatMap((g) => g.fields).find((f) => f.section === "coach" && f.key === "language")!;
const language = (code: unknown) => optionLabel(languageField, String(code)) || String(code);
function summary(g: Group): string {
  const v = s.value;
  if (!v) return "";
  switch (g.id) {
    case "aide":
      return [t("settings.sum.level", { n: Number(v.coach.help_level) }), t(v.coach.trust_proof ? "settings.sum.proof_settles" : "settings.sum.percent_only"),
              language(v.coach.language)].join(" · ");
    case "analyse": {
      const all = Object.keys((v.streetclip.countries ?? {}) as object).length;
      const active = all - ((v.streetclip.exclude_countries ?? []) as string[]).length;
      const vision = v.vision.enabled ? String(v.vision.model).split("/").pop() : t("settings.sum.deep_off");
      return `${vision} · ${t("settings.sum.candidates", { n: active })}`;
    }
    case "indices":
      return `${t(v.metas.enabled ? (v.metas.include_seed ? "settings.sum.metas_seed" : "settings.sum.your_metas") : "settings.sum.metas_off")} · ${t(v.plonkit.enabled ? "settings.sum.plonkit_on" : "settings.sum.plonkit_off")}`;
    case "carte":
      return v.map.enabled ? `${t(v.plonk.enabled ? "settings.sum.zones" : "settings.sum.countries_only")} · ${t("settings.sum.zoom", { n: Number(v.map.max_zoom) })}` : t("settings.sum.map_off");
    case "capture": {
      const notify = t(v.capture.notify ? (v.capture.sound ? "settings.sum.notify_sound" : "settings.sum.notify") : "settings.sum.silent");
      const keep = Number(v.capture.keep_last);
      const copies = v.capture.save_to_disk ? (keep ? t("settings.sum.kept", { n: keep }) : t("settings.sum.all_kept")) : t("settings.sum.no_copy");
      return `${notify} · ${copies}`;
    }
    case "verrous": {
      if (!v.locks.enabled) return t("settings.sum.locks_off");
      const auto = [v.locks.auto_country ? t("settings.sum.country") : "", v.locks.auto_region ? t("settings.sum.region") : ""]
        .filter(Boolean).join(t("settings.sum.and"));
      return `${auto ? t("settings.sum.coach_sets", { what: auto }) : t("settings.sum.only_you")}${v.locks.propose_city ? t("settings.sum.city_suggested") : ""}`;
    }
    case "stockage":
      return t("settings.sum.caches", { size: t("unit.mb", { n: num(Number(v.storage.max_cache_mb)) }) });
    case "jeu-de-test":
      return t(v.dataset.enabled ? (v.dataset.ask_guessed ? "settings.sum.asked" : "settings.sum.found_yes_no") : "settings.sum.dataset_off");
    case "moteur": {
      const server = fileOnly.value?.server;
      const where = server ? `${server.host.value}:${server.port.value}` : "";
      return [where, v.debug?.enabled ? t("settings.sum.debug_on") : ""].filter(Boolean).join(" · ");
    }
  }
  return "";
}

const basic = (g: Group) => g.fields.filter((f) => !f.advanced);
const advanced = (g: Group) => g.fields.filter((f) => f.advanced);
const reserved = (g: Group) =>
  g.fileSections.flatMap((section) =>
    Object.entries(fileOnly.value?.[section] ?? {}).map(([key, entry]) => ({ id: `${section}.${key}`, ...entry })),
  );
const shown = (v: unknown) => (Array.isArray(v) ? v.join(", ") : v === "" ? t("settings.empty_default") : String(v));
const button = "rounded-md border px-3 py-1.5 text-papier disabled:opacity-50";
</script>

<template>
  <section aria-labelledby="reglages-titre" class="pt-4">
    <h2 id="reglages-titre" class="atlas text-[1.6rem] text-papier">{{ t("settings.title") }}</h2>
    <p class="mt-1 text-[0.85rem] text-courbe">{{ t("settings.applies_now") }}</p>

    <p v-if="!s" class="mt-4 text-courbe">{{ t("settings.loading") }}</p>

    <div v-else class="mt-3">
      <datalist id="modeles-nvidia">
        <option v-for="m in models" :key="m" :value="m" />
      </datalist>

      <Section v-for="g in GROUPS" :id="`reglage-${g.id}`" :key="g.id" :title="groupTitle(g)" :summary="summary(g)" :open="false" tone="papier">
        <div class="space-y-5 py-1">
          <div v-if="g.id === 'capture'" class="flex flex-wrap items-center gap-3">
            <button type="button" :class="[button, 'border-courbe hover:bg-papier/10']"
                    :disabled="!engine.connected || engine.busy || engine.capture.starting" @click="reselectWindow">
              {{ t("settings.change_window") }}
            </button>
            <span class="text-[0.85rem] text-courbe">{{ t("settings.change_window_hint") }}</span>
          </div>

          <template v-for="f in basic(g)" :key="fieldId(f)">
            <SettingField :field="f" :settings="s" :status="status[fieldId(f)]"
                          @save="(section, key, v) => save(f, section, key, v)" @invalid="(text) => invalid(f, text)" />

            <!-- Extras specific to some settings -->
            <div v-if="f.section === 'vision' && f.key === 'enabled'" class="-mt-2 space-y-1.5">
              <label for="cle-api" class="block text-papier">{{ t("settings.api_key") }}</label>
              <p class="text-[0.85rem] text-courbe">
                <template v-if="engine.vision.key">
                  {{ t("settings.key_stored", { end: engine.vision.key.end, source: t(engine.vision.key.source === "env" ? "settings.key_source.env" : "settings.key_source.file") }) }}
                </template>
                <template v-else>{{ t("settings.key_none") }}</template>
                {{ t("settings.key_where_before") }}
                <code class="text-papier">~/.config/geonesclick/nvapi.key</code>{{ t("settings.key_where_after") }}
              </p>
              <form class="flex flex-wrap gap-2" @submit.prevent="storeKey(keyInput)">
                <input id="cle-api" v-model="keyInput" type="password" autocomplete="off" spellcheck="false"
                       class="min-w-0 flex-1 rounded-md border border-courbe-fonce bg-relief px-3 py-1.5 text-papier"
                       :placeholder="engine.vision.key ? t('settings.new_key') : 'nvapi-…'" />
                <button type="submit" :class="[button, 'border-lac/50 hover:bg-lac/10']" :disabled="!keyInput.trim() || engine.busy">
                  {{ t("settings.save") }}
                </button>
                <button v-if="engine.vision.key?.source === 'file'" type="button" :class="[button, 'border-alerte/50 hover:bg-alerte/10']"
                        :disabled="engine.busy" @click="storeKey('')">
                  {{ t("settings.forget") }}
                </button>
              </form>
              <p v-if="keyStatus" class="text-[0.85rem]" :class="keyStatus.tone === 'ok' ? 'text-foret' : 'text-alerte'" role="status">
                {{ keyStatus.text }}
              </p>
            </div>
            <div v-if="f.section === 'vision' && f.key === 'model'" class="-mt-3 flex flex-wrap items-center gap-3">
              <span class="text-[0.85rem] text-courbe">{{ models.length ? t("settings.models_count", { n: models.length }) : t("settings.models_unavailable") }}</span>
              <button type="button" :class="[button, 'border-lac/50 hover:bg-lac/10']" :disabled="testing || !s.vision.enabled" @click="runTest">
                {{ t(testing ? "settings.testing" : "settings.test_model") }}
              </button>
              <p v-if="test && test.model === s.vision.model" class="text-[0.85rem]" :class="test.ok ? 'text-foret' : 'text-alerte'" role="status">
                {{ test.text }}
              </p>
            </div>
            <p v-if="f.section === 'metas' && f.key === 'enabled'" class="-mt-3 text-[0.85rem]"
               :class="engine.metas.error ? 'text-alerte' : 'text-courbe'">
              {{ engine.metas.message }}
            </p>
            <div v-if="f.section === 'plonkit' && f.key === 'refresh_days'" class="-mt-2 space-y-2">
              <p class="text-[0.85rem]" :class="engine.plonkit.status === 'error' ? 'text-alerte' : 'text-courbe'" role="status">
                {{ engine.plonkit.status === "off" ? t("settings.plonkit_off") : engine.plonkit.message || t("settings.waiting") }}
              </p>
              <button type="button" :class="[button, 'border-foret/50 hover:bg-foret/10']"
                      :disabled="!engine.plonkit.enabled || engine.plonkit.status === 'busy' || engine.busy" @click="refreshPlonkit">
                {{ t(engine.plonkit.status === "busy" ? "settings.updating" : "settings.update_now") }}
              </button>
            </div>
            <p v-if="f.section === 'plonk' && f.key === 'enabled'" class="-mt-3 text-[0.85rem] text-courbe" role="status">
              {{ t("settings.plonk_status", { message: engine.plonk.message }) }}
            </p>
          </template>

          <StoragePanel v-if="g.id === 'stockage'" :max-mb="Number(s.storage.max_cache_mb)" />

          <details v-if="advanced(g).length" class="rounded-md border border-courbe-fonce/70 px-3 py-2">
            <summary class="cursor-pointer text-[0.9rem] text-courbe hover:text-papier">{{ t("settings.advanced") }} ({{ advanced(g).length }})</summary>
            <div class="mt-3 space-y-5">
              <SettingField v-for="f in advanced(g)" :key="fieldId(f)" :field="f" :settings="s" :status="status[fieldId(f)]"
                            @save="(section, key, v) => save(f, section, key, v)" @invalid="(text) => invalid(f, text)" />
            </div>
          </details>

          <div v-if="reserved(g).length" class="rounded-md border border-dashed border-courbe-fonce px-3 py-2">
            <p class="text-[0.9rem] text-courbe">
              {{ t("settings.file_only", { file: "~/.config/geonesclick/config.toml" }) }}
            </p>
            <dl class="mt-2 space-y-2 text-[0.85rem]">
              <div v-for="r in reserved(g)" :key="r.id">
                <dt class="text-papier">{{ fileOnlyLabel(r.id) }} <span class="text-courbe">({{ r.id }})</span></dt>
                <dd class="break-all text-courbe">{{ shown(r.value) }}</dd>
                <dd class="text-courbe/80 italic">{{ r.why }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </Section>
    </div>
  </section>
</template>
