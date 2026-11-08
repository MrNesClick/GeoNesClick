<script setup lang="ts">
// Settings screen: EVERYTHING is configurable. Seven collapsible groups in the coach's format (title + one-line
// summary), described in settingsSchema.ts; fine-grained settings are under "Advanced". Each change applies and
// is saved right away. File-only settings (security) are shown read-only, with their reason and where to
// change them.
import { onMounted, reactive, ref } from "vue";
import type { FileOnly, Settings } from "../engine";
import { engine, fr, getJSON, refreshPlonkit, reselectWindow, saveApiKey, saveSetting, testModel } from "../engine";
import type { Field, Group } from "../settingsSchema";
import { FILE_ONLY_LABELS, GROUPS } from "../settingsSchema";
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
  status[id] = { tone: "busy", text: "Enregistrement…" };
  const r = await saveSetting(section, key, value);
  if (r.error) {
    status[id] = { tone: "error", text: r.error };
    await load(); // the screen goes back to the value actually in effect
    return;
  }
  if (s.value) s.value[section][key] = value;
  status[id] = { tone: "ok", text: r.restart ? "Enregistré : pris en compte au prochain démarrage." : "Enregistré." };
  if (!r.restart) timers[id] = setTimeout(() => delete status[id], 2500);
}
const invalid = (f: Field, text: string) => (status[fieldId(f)] = { tone: "error", text });

// NVIDIA API key: entered here, stored by the engine in ~/.config/geonesclick/nvapi.key (readable by you only).
const keyInput = ref("");
const keyStatus = ref<{ tone: "ok" | "error"; text: string } | null>(null);
async function storeKey(value: string) {
  if (value && !value.trim().startsWith("nvapi-")) {
    keyStatus.value = { tone: "error", text: "Une clé NVIDIA commence par « nvapi- »." };
    return;
  }
  const error = await saveApiKey(value);
  keyStatus.value = error ? { tone: "error", text: error } : { tone: "ok", text: value ? "Clé enregistrée." : "Clé oubliée." };
  if (!error) keyInput.value = "";
  models.value = (await getJSON<{ models: string[] }>("/models"))?.models ?? [];
}

async function runTest() {
  const model = String(s.value?.vision.model ?? "");
  testing.value = true;
  const r = await testModel(model);
  testing.value = false;
  test.value = r.ok
    ? { model, ok: true, text: `Accepte les images, répond en ${fr(r.seconds ?? 0)} s.` }
    : { model, ok: false, text: r.error ?? "Échec du test." };
}

// --- One-line summaries, readable when the section is collapsed ---------------------------------------
const LANG: Record<string, string> = {
  fr: "français", en: "anglais", es: "espagnol", de: "allemand", it: "italien", pt: "portugais",
};
function summary(g: Group): string {
  const v = s.value;
  if (!v) return "";
  switch (g.id) {
    case "aide":
      return `niveau ${v.coach.help_level} · ${v.coach.trust_proof ? "une preuve tranche" : "pourcentages seuls"} · ${LANG[String(v.coach.language)] ?? v.coach.language}`;
    case "analyse": {
      const all = Object.keys((v.streetclip.countries ?? {}) as object).length;
      const active = all - ((v.streetclip.exclude_countries ?? []) as string[]).length;
      const vision = v.vision.enabled ? String(v.vision.model).split("/").pop() : "approfondie coupée";
      return `${vision} · ${active} pays candidats`;
    }
    case "indices":
      return `${v.metas.enabled ? (v.metas.include_seed ? "metas + amorce" : "tes metas") : "metas coupées"} · Plonk It ${v.plonkit.enabled ? "activé" : "coupé"}`;
    case "carte":
      return v.map.enabled ? `${v.plonk.enabled ? "zones probables" : "pays seulement"} · zoom ${v.map.max_zoom}` : "désactivée";
    case "capture": {
      const notify = v.capture.notify ? (v.capture.sound ? "notification + son" : "notification") : "silencieuse";
      const keep = Number(v.capture.keep_last);
      const copies = v.capture.save_to_disk ? (keep ? `${keep} gardées` : "toutes gardées") : "sans copie";
      return `${notify} · ${copies}`;
    }
    case "verrous": {
      if (!v.locks.enabled) return "désactivés";
      const auto = [v.locks.auto_country ? "pays" : "", v.locks.auto_region ? "région" : ""].filter(Boolean).join(" et ");
      return `${auto ? `le coach fixe ${auto}` : "toi seul le dis"}${v.locks.propose_city ? " · ville proposée" : ""}`;
    }
    case "stockage":
      return `caches limités à ${v.storage.max_cache_mb} Mo`;
    case "jeu-de-test":
      return v.dataset.enabled ? (v.dataset.ask_guessed ? "pays répondu demandé" : "trouvé ? oui / non") : "désactivé";
    case "moteur": {
      const server = fileOnly.value?.server;
      const where = server ? `${server.host.value}:${server.port.value}` : "";
      return [where, v.debug?.enabled ? "débogage activé" : ""].filter(Boolean).join(" · ");
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
const shown = (v: unknown) => (Array.isArray(v) ? v.join(", ") : v === "" ? "(vide : valeur par défaut)" : String(v));
const button = "rounded-md border px-3 py-1.5 text-papier disabled:opacity-50";
</script>

<template>
  <section aria-labelledby="reglages-titre" class="pt-4">
    <h2 id="reglages-titre" class="atlas text-[1.6rem] text-papier">Réglages</h2>
    <p class="mt-1 text-[0.85rem] text-courbe">Chaque changement s'applique et s'enregistre tout de suite.</p>

    <p v-if="!s" class="mt-4 text-courbe">Chargement des réglages…</p>

    <div v-else class="mt-3">
      <datalist id="modeles-nvidia">
        <option v-for="m in models" :key="m" :value="m" />
      </datalist>

      <Section v-for="g in GROUPS" :id="`reglage-${g.id}`" :key="g.id" :title="g.title" :summary="summary(g)" :open="false" tone="papier">
        <div class="space-y-5 py-1">
          <div v-if="g.id === 'capture'" class="flex flex-wrap items-center gap-3">
            <button type="button" :class="[button, 'border-courbe hover:bg-papier/10']"
                    :disabled="!engine.connected || engine.busy || engine.capture.starting" @click="reselectWindow">
              Changer de fenêtre
            </button>
            <span class="text-[0.85rem] text-courbe">Autre navigateur, écran ou résolution : rouvre le sélecteur de GNOME.</span>
          </div>

          <template v-for="f in basic(g)" :key="fieldId(f)">
            <SettingField :field="f" :settings="s" :status="status[fieldId(f)]"
                          @save="(section, key, v) => save(f, section, key, v)" @invalid="(t) => invalid(f, t)" />

            <!-- Extras specific to some settings -->
            <div v-if="f.section === 'vision' && f.key === 'enabled'" class="-mt-2 space-y-1.5">
              <label for="cle-api" class="block text-papier">Clé API NVIDIA</label>
              <p class="text-[0.85rem] text-courbe">
                <template v-if="engine.vision.key">
                  Enregistrée (…{{ engine.vision.key.end }}, {{ engine.vision.key.source }}).
                </template>
                <template v-else>Aucune : l'analyse approfondie et la lecture des marques sont coupées.</template>
                Gratuite sur build.nvidia.com (« Get API Key »). Rangée dans
                <code class="text-papier">~/.config/geonesclick/nvapi.key</code>, lisible par toi seul ; jamais réaffichée.
              </p>
              <form class="flex flex-wrap gap-2" @submit.prevent="storeKey(keyInput)">
                <input id="cle-api" v-model="keyInput" type="password" autocomplete="off" spellcheck="false"
                       class="min-w-0 flex-1 rounded-md border border-courbe-fonce bg-relief px-3 py-1.5 text-papier"
                       :placeholder="engine.vision.key ? 'Nouvelle clé (nvapi-…)' : 'nvapi-…'" />
                <button type="submit" :class="[button, 'border-lac/50 hover:bg-lac/10']" :disabled="!keyInput.trim() || engine.busy">
                  Enregistrer
                </button>
                <button v-if="engine.vision.key?.source === 'fichier'" type="button" :class="[button, 'border-alerte/50 hover:bg-alerte/10']"
                        :disabled="engine.busy" @click="storeKey('')">
                  Oublier
                </button>
              </form>
              <p v-if="keyStatus" class="text-[0.85rem]" :class="keyStatus.tone === 'ok' ? 'text-foret' : 'text-alerte'" role="status">
                {{ keyStatus.text }}
              </p>
            </div>
            <div v-if="f.section === 'vision' && f.key === 'model'" class="-mt-3 flex flex-wrap items-center gap-3">
              <span class="text-[0.85rem] text-courbe">{{ models.length ? `${models.length} modèles NVIDIA disponibles` : "liste des modèles indisponible" }}</span>
              <button type="button" :class="[button, 'border-lac/50 hover:bg-lac/10']" :disabled="testing || !s.vision.enabled" @click="runTest">
                {{ testing ? "Test en cours…" : "Tester ce modèle" }}
              </button>
              <p v-if="test && test.model === s.vision.model" class="text-[0.85rem]" :class="test.ok ? 'text-foret' : 'text-alerte'" role="status">
                {{ test.text }}
              </p>
            </div>
            <p v-if="f.section === 'metas' && f.key === 'enabled'" class="-mt-3 text-[0.85rem]"
               :class="engine.metas.message.startsWith('metas indisponibles') ? 'text-alerte' : 'text-courbe'">
              {{ engine.metas.message }}
            </p>
            <div v-if="f.section === 'plonkit' && f.key === 'refresh_days'" class="-mt-2 space-y-2">
              <p class="text-[0.85rem]" :class="engine.plonkit.status === 'error' ? 'text-alerte' : 'text-courbe'" role="status">
                {{ engine.plonkit.status === "off" ? "Guides Plonk It désactivés." : engine.plonkit.message || "En attente…" }}
              </p>
              <button type="button" :class="[button, 'border-foret/50 hover:bg-foret/10']"
                      :disabled="!engine.plonkit.enabled || engine.plonkit.status === 'busy' || engine.busy" @click="refreshPlonkit">
                {{ engine.plonkit.status === "busy" ? "Mise à jour en cours…" : "Mettre à jour maintenant" }}
              </button>
            </div>
            <p v-if="f.section === 'plonk' && f.key === 'enabled'" class="-mt-3 text-[0.85rem] text-courbe" role="status">
              PLONK : {{ engine.plonk.message }}
            </p>
          </template>

          <StoragePanel v-if="g.id === 'stockage'" :max-mb="Number(s.storage.max_cache_mb)" />

          <details v-if="advanced(g).length" class="rounded-md border border-courbe-fonce/70 px-3 py-2">
            <summary class="cursor-pointer text-[0.9rem] text-courbe hover:text-papier">Avancé ({{ advanced(g).length }})</summary>
            <div class="mt-3 space-y-5">
              <SettingField v-for="f in advanced(g)" :key="fieldId(f)" :field="f" :settings="s" :status="status[fieldId(f)]"
                            @save="(section, key, v) => save(f, section, key, v)" @invalid="(t) => invalid(f, t)" />
            </div>
          </details>

          <div v-if="reserved(g).length" class="rounded-md border border-dashed border-courbe-fonce px-3 py-2">
            <p class="text-[0.9rem] text-courbe">
              Réservé au fichier <code class="text-papier">~/.config/geonesclick/config.toml</code>, par sécurité :
            </p>
            <dl class="mt-2 space-y-2 text-[0.85rem]">
              <div v-for="r in reserved(g)" :key="r.id">
                <dt class="text-papier">{{ FILE_ONLY_LABELS[r.id] ?? r.id }} <span class="text-courbe">({{ r.id }})</span></dt>
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
