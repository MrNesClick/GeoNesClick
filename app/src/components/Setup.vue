<script setup lang="ts">
// First-launch assistant (AppImage), decided with the user on 2026-11-07:
// - in STEPS, the required part first;
// - 100 % transparent: EVERYTHING that will be downloaded (what, from where, size, licence, when, what leaves your
//   machine) is shown BEFORE a single byte, package by package if you want; one consent for the required block,
//   then each option has its Accept / Skip, with my recommendation pre-ticked;
// - the big downloads run while you choose your options; these are written BEFORE the engine's first
//   start (it never downloads a declined option). Everything stays editable in the Settings.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { num } from "../engine";
import { hasKey, i18n, LANGS, setLanguage, t, uiLanguage, type Key, type Lang } from "../i18n";

// Language: English by default, chosen on the first screen (decided with the user on 2026-11-12), written to
// coach.language with the other choices; each catalog names its own language ("Français", "English").
const LANGUAGE_NAMES = Object.fromEntries(LANGS.map((l) => [l, t("language.name", undefined, l)])) as Record<Lang, string>;
const chooseLanguage = (lang: string) => setLanguage(uiLanguage(lang));

interface Download {
  id: string; hosts: string[]; size_mb: number; license: string;
  when: "installation" | "option" | "on_demand" | "continuous"; required: boolean; option?: string;
}
interface Package { name: string; version: string; size: number; license: string; note?: string }
/** label: catalog key of its name (setup.rs, system_checks). */
interface Check { label: Key; ok: boolean; package: string }
interface Status {
  bundled: boolean; needed: boolean; version: string | null; installed: string | null; engine_ready: boolean; gpu: boolean;
  checks: Check[]; downloads: { download: Download[] }; packages_cuda: Package[]; packages_cpu: Package[];
}

const emit = defineEmits<{ done: [] }>();
const status = ref<Status | null>(null);
const step = ref<"system" | "components" | "options" | "install">("system");
const STEPS = ["system", "components", "options", "install"] as const;
const stepIndex = computed(() => STEPS.indexOf(step.value));
const variant = ref<"cuda" | "cpu">("cpu");
const showPackages = ref(false);
let invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

async function load() {
  ({ invoke } = await import("@tauri-apps/api/core"));
  status.value = (await invoke("setup_status")) as Status;
  variant.value = status.value.gpu ? "cuda" : "cpu";
  restoreChoices();
  if (status.value.engine_ready) {
    // Installed earlier, window closed before the end: only the options are left, nothing is downloaded again.
    installing.value = true;
    installDone.value = true;
    step.value = "options";
  } else if (status.value.checks.every((c) => c.ok)) step.value = "components";
}

// --- list of downloads -----------------------------------------------------------------------------
const all = computed(() => status.value?.downloads?.download ?? []);
const byId = (id: string) => all.value.find((d) => d.id === id);
const packages = computed(() => (variant.value === "cuda" ? status.value?.packages_cuda : status.value?.packages_cpu) ?? []);
const required = computed(() => all.value.filter((d) => d.required && (variant.value === "cuda" ? d.id !== "pytorch-cpu" : true)));
const packagesMb = computed(() => {
  const mb = packages.value.reduce((n, p) => n + p.size, 0) / 1e6;
  return variant.value === "cpu" ? mb + (byId("pytorch-cpu")?.size_mb ?? 0) : mb;
});
const sizeOf = (d: Download) => (d.id === "packages" ? packagesMb.value : d.size_mb);
const requiredMb = computed(() => required.value.filter((d) => d.id !== "pytorch-cpu").reduce((n, d) => n + sizeOf(d), 0));
const mb = (n: number) => (n >= 1000 ? t("unit.gb", { n: num(n / 1000) }) : n >= 1 ? t("unit.mb", { n: Math.round(n) }) : n ? t("setup.size.less_mb") : "—");
/** A text of a download in the UI's language (download.<id>.<field>); the licence falls back on downloads.toml's. */
const dl = (d: Download, field: "what" | "why" | "license" | "sends") => {
  const key = `download.${d.id}.${field}`;
  return hasKey(key) ? t(key) : field === "license" ? d.license : "";
};
// Short names for the summary; the full text (why, sources, licence) stays under the details.
const short = (d: Download) => {
  const key = `setup.short.${d.id}`;
  return hasKey(key) ? t(key) : dl(d, "what");
};
// What leaves the machine, in plain words (the full text stays under the details).
const sent = (d: Download) => {
  const key = `setup.sent.${d.id}`;
  return hasKey(key) ? t(key) : t("setup.sent.fallback", { what: dl(d, "what"), sends: dl(d, "sends") });
};
const optional = computed(() => all.value.filter((x) => x.when === "option" || x.when === "on_demand"));
const continuous = computed(() => all.value.filter((x) => x.when === "continuous"));
const missing = computed(() => (status.value?.checks ?? []).filter((c) => !c.ok));
const aptCommand = computed(() => `sudo apt install ${missing.value.map((c) => c.package).join(" ")}`);

// --- installation (in the background) --------------------------------------------------------------
const phase = ref("");
const lines = ref<string[]>([]);
const installDone = ref<boolean | null>(null); // null: running; true / false: finished
const failure = ref(""); // likely cause of a failure (site down, disk full), from setup.rs; empty: see the log
const installing = ref(false);
// Phases announced by install-engine.sh ("PHASE <name>"), in order.
const PHASES = ["python", "paquets", "moteur", "modele", "finition"] as const;
// The log follows its last line, like a terminal.
const logBox = ref<HTMLElement | null>(null);
watch(lines, () => nextTick(() => logBox.value && (logBox.value.scrollTop = logBox.value.scrollHeight)));
const phaseIndex = computed(() => (installDone.value === true ? PHASES.length : PHASES.findIndex((p) => p === phase.value)));
let unlisten: (() => void) | null = null;
async function startInstall() {
  const { listen } = await import("@tauri-apps/api/event");
  unlisten?.(); // a retry must not add a second listener
  unlisten = await listen<{ phase: string | null; line: string | null; done: boolean; ok: boolean; reason: string | null }>(
    "setup-progress", ({ payload: p }) => {
      if (p.phase) phase.value = p.phase;
      if (p.line && !p.line.startsWith("PHASE ")) lines.value = [...lines.value.slice(-199), p.line];
      if (p.done) {
        installDone.value = p.ok;
        failure.value = p.reason ?? "";
      }
    });
  installing.value = true;
  installDone.value = null;
  failure.value = "";
  lines.value = [];
  if (step.value === "components") step.value = "options"; // options are chosen during the download
  try {
    await invoke("setup_install", { variant: variant.value });
  } catch (e) {
    installDone.value = false;
    lines.value = [...lines.value, String(e)];
  }
}
onBeforeUnmount(() => unlisten?.());

// --- options: Accept / Skip, recommendation pre-ticked ---------------------------------------------
// Label and detail: setup.option.<id> and setup.option.<id>.detail in the catalogs.
interface Option { id: "places" | "plonkit" | "map" | "plonk"; recommended: boolean; settings: Record<string, Record<string, unknown>> }
const OPTIONS: Option[] = [
  { id: "places", recommended: true, settings: { rules: { places: true, detail: true } } },
  { id: "plonkit", recommended: true, settings: { plonkit: { enabled: true } } },
  { id: "map", recommended: true, settings: { map: { enabled: true } } },
  { id: "plonk", recommended: false, settings: { plonk: { enabled: true } } },
];
const OFF: Record<string, Record<string, Record<string, unknown>>> = {
  places: { rules: { places: false, detail: false } }, plonkit: { plonkit: { enabled: false } },
  map: { map: { enabled: false } }, plonk: { plonk: { enabled: false } },
};
const chosen = ref<Record<string, boolean>>(Object.fromEntries(OPTIONS.map((o) => [o.id, o.recommended])));
const key = ref("");
// NVIDIA keys start with "nvapi-" (the engine refuses anything else too).
const keyError = computed(() => {
  const k = key.value.trim();
  if (!k) return "";
  if (!k.startsWith("nvapi-")) return t("settings.key_prefix");
  if (/\s/.test(k) || k.length < 20) return t("setup.key.incomplete");
  return "";
});
// Without a key, going on must be a conscious choice: text and signs are not read.
const noKey = ref(false);
const shortcuts = ref(true);
const helpLevel = ref(4);
// Choices survive a closed window (the API key never: it is a secret); forgotten once the installation is done.
const SAVED = "geonesclick.setup";
function restoreChoices() {
  try {
    const saved = JSON.parse(localStorage.getItem(SAVED) ?? "null");
    if (!saved) return;
    Object.assign(chosen.value, saved.chosen ?? {});
    if (typeof saved.shortcuts === "boolean") shortcuts.value = saved.shortcuts;
    if (typeof saved.helpLevel === "number") helpLevel.value = saved.helpLevel;
    if (typeof saved.noKey === "boolean") noKey.value = saved.noKey;
    if (saved.variant === "cuda" || saved.variant === "cpu") variant.value = saved.variant;
    if (typeof saved.language === "string") chooseLanguage(saved.language);
  } catch {
    /* storage unavailable or damaged: the recommended choices stay */
  }
}
watch(
  () => ({ chosen: chosen.value, shortcuts: shortcuts.value, helpLevel: helpLevel.value, noKey: noKey.value, variant: variant.value,
           language: i18n.lang }),
  (state) => {
    try {
      localStorage.setItem(SAVED, JSON.stringify(state));
    } catch {
      /* storage unavailable: choices are simply not remembered */
    }
  },
  { deep: true },
);
const optionsValid = computed(() => !keyError.value && (key.value.trim() !== "" || noKey.value));
const LEVELS = [1, 2, 3, 4] as const;
const choices = computed(() => {
  const out: Record<string, Record<string, unknown>> = { coach: { help_level: helpLevel.value, language: i18n.lang } };
  for (const o of OPTIONS) {
    for (const [section, values] of Object.entries(chosen.value[o.id] ? o.settings : OFF[o.id])) {
      out[section] = { ...(out[section] ?? {}), ...values };
    }
  }
  if (!key.value.trim()) out.plonkit = { ...(out.plonkit ?? {}), pretranslate: false };
  return out;
});

// --- end: options written, shortcuts, first start ---------------------------------------------------
const finishing = ref(false);
const finishError = ref("");
async function finish() {
  finishing.value = true;
  finishError.value = "";
  try {
    await invoke("setup_apply", { choices: choices.value, apiKey: key.value.trim() || null });
    if (shortcuts.value) {
      await invoke("setup_shortcuts").catch((e) => (finishError.value = t("setup.shortcuts_failed", { error: String(e) })));
    }
    await invoke("restart_engine");
    try {
      localStorage.removeItem(SAVED);
    } catch {
      /* nothing to forget */
    }
    emit("done");
  } catch (e) {
    finishError.value = String(e);
  } finally {
    finishing.value = false;
  }
}

onMounted(load);

const box = "rounded-md border border-courbe-fonce px-3 py-2";
const disclosure = "cursor-pointer select-none py-1 text-[1.05rem] text-papier underline-offset-4 hover:underline";
const primary = "rounded-md bg-papier px-6 py-2.5 text-[1.05rem] font-bold text-encre hover:bg-white disabled:opacity-40";
const secondary = "rounded-md border border-courbe-fonce px-5 py-2.5 text-[1.05rem] text-papier hover:bg-relief disabled:opacity-40";
const check = "mt-1 h-5 w-5 shrink-0 cursor-pointer accent-lac";
</script>

<template>
  <main class="flex h-screen flex-col bg-encre text-[1.05rem]">
    <header class="border-b border-courbe-fonce px-6 pt-5 pb-4">
      <div class="flex items-baseline justify-between gap-4">
        <h1 class="text-[1.7rem] font-bold text-papier">{{ t("setup.title") }}</h1>
        <div class="flex items-baseline gap-4">
          <!-- Each language in its own name: whoever does not read the current one still finds theirs. -->
          <label class="flex items-baseline gap-2 text-[1rem] text-courbe">
            <span>{{ t("language.label") }}</span>
            <select :value="i18n.lang" class="rounded-md border border-courbe-fonce bg-relief px-2 py-1 text-papier"
                    @change="chooseLanguage(($event.target as HTMLSelectElement).value)">
              <option v-for="l in LANGS" :key="l" :value="l" :lang="l">{{ LANGUAGE_NAMES[l] }}</option>
            </select>
          </label>
          <span v-if="status?.version" class="text-[1rem] text-courbe">{{ t("setup.version", { version: status.version }) }}</span>
        </div>
      </div>
      <p v-if="status?.installed && status.installed !== status.version" class="mt-1 text-[1.05rem] text-courbe">
        {{ t("setup.update", { from: status.installed, to: status.version ?? "" }) }}
      </p>
      <ol class="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-[1rem]" :aria-label="t('setup.steps_aria')">
        <li v-for="(s, i) in STEPS" :key="s" class="flex items-center gap-2"
            :aria-current="i === stepIndex ? 'step' : undefined">
          <span class="grid h-6 w-6 place-items-center rounded-full text-[0.85rem] font-bold"
                :class="i < stepIndex ? 'bg-foret text-encre' : i === stepIndex ? 'bg-papier text-encre' : 'border border-courbe-fonce text-courbe'">
            {{ i < stepIndex ? "✓" : i + 1 }}
          </span>
          <span :class="i === stepIndex ? 'font-bold text-papier' : 'text-courbe'">{{ t(`setup.step.${s}`) }}</span>
          <span v-if="i < STEPS.length - 1" class="mx-1 h-px w-6 bg-courbe-fonce" aria-hidden="true" />
        </li>
      </ol>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-5">
      <p v-if="!status" class="text-courbe">{{ t("setup.checking") }}</p>

      <!-- 1. System -->
      <section v-else-if="step === 'system'" class="space-y-4" aria-labelledby="etape-systeme">
        <h2 id="etape-systeme" class="text-[1.15rem] font-bold text-papier">{{ t("setup.system.title") }}</h2>
        <p class="text-[1.05rem] text-courbe">{{ t("setup.system.intro") }}</p>
        <ul :class="box" class="space-y-1">
          <li v-for="c in status.checks" :key="c.label" class="flex gap-2">
            <span :class="c.ok ? 'text-foret' : 'text-alerte'">{{ c.ok ? "✓" : "✗" }}</span>
            <span class="flex-1 text-papier">{{ t(c.label) }}</span>
            <code v-if="!c.ok" class="text-courbe">{{ c.package }}</code>
          </li>
        </ul>
        <div v-if="missing.length" class="space-y-2">
          <p class="text-papier">{{ t("setup.system.missing") }}</p>
          <code class="block rounded bg-relief px-3 py-2 text-papier select-all">{{ aptCommand }}</code>
        </div>
      </section>

      <!-- 2. Components: a summary, the full list under the details -->
      <section v-else-if="step === 'components'" class="space-y-6" aria-labelledby="etape-composants">
        <div>
          <div class="flex items-baseline justify-between">
            <h2 id="etape-composants" class="text-[1.15rem] font-bold text-papier">{{ t("setup.required.title") }}</h2>
            <span class="tabular-nums font-bold text-papier">{{ mb(requiredMb) }}</span>
          </div>
          <ul class="mt-2 text-[1.05rem]">
            <li v-for="d in required.filter((x) => x.id !== 'pytorch-cpu')" :key="d.id"
                class="flex justify-between gap-2 border-t border-courbe-fonce/50 py-1">
              <span class="text-papier">{{ short(d) }}</span>
              <span class="tabular-nums text-courbe">{{ mb(sizeOf(d)) }}</span>
            </li>
          </ul>
          <label v-if="status.gpu" class="mt-2 flex items-center gap-3 text-[1.05rem] text-papier">
            <input type="checkbox" :class="check" :checked="variant === 'cpu'" @change="variant = variant === 'cpu' ? 'cuda' : 'cpu'" />
            {{ t("setup.use_cpu") }}
          </label>
          <p v-else class="mt-2 text-[1rem] text-courbe">{{ t("setup.no_nvidia") }}</p>
          <p class="mt-1 text-[1rem] text-courbe">{{ t("setup.where") }}</p>
          <details class="mt-3">
            <summary :class="disclosure">{{ t("setup.sources") }}</summary>
            <table class="mt-2 w-full text-[1rem]">
              <tbody>
                <tr v-for="d in all" :key="d.id" class="border-t border-courbe-fonce/50 align-top">
                  <td class="py-1 pr-2 text-papier">{{ dl(d, "what") }}<span class="block text-courbe">{{ dl(d, "why") }}</span></td>
                  <td class="py-1 pr-2 text-courbe">{{ d.hosts.join(", ") }}<span class="block">{{ dl(d, "license") }} · {{ t(`setup.when.${d.when}`) }}</span></td>
                  <td class="py-1 text-right tabular-nums text-papier">{{ d.id === "pytorch-cpu" ? t("setup.included") : mb(sizeOf(d)) }}</td>
                </tr>
              </tbody>
            </table>
            <button type="button" class="mt-2 text-courbe underline underline-offset-2 hover:text-papier"
                    @click="showPackages = !showPackages">
              {{ t(showPackages ? "setup.hide_packages" : "setup.show_packages", { n: packages.length }) }}
            </button>
            <table v-if="showPackages" class="mt-1 w-full text-[0.95rem]">
              <tbody>
                <tr v-for="p in packages" :key="p.name" class="border-t border-courbe-fonce/40">
                  <td class="py-0.5 pr-2 text-papier">{{ p.name }} {{ p.version }}</td>
                  <td class="py-0.5 pr-2 text-courbe">{{ p.license }}</td>
                  <td class="py-0.5 text-right tabular-nums text-courbe">{{ p.note ? p.note : mb(p.size / 1e6) }}</td>
                </tr>
              </tbody>
            </table>
          </details>
        </div>

        <div>
          <h2 class="text-[1.15rem] font-bold text-papier">{{ t("setup.optional.title") }}</h2>
          <p class="mt-1 text-[1.05rem] text-courbe">
            <template v-for="(d, i) in optional" :key="d.id">{{ i ? " · " : "" }}{{ short(d) }} ({{ mb(d.size_mb) }})</template>
          </p>
          <p class="text-[1rem] text-courbe">{{ t("setup.optional.next") }}</p>
        </div>

        <div>
          <h2 class="text-[1.15rem] font-bold text-papier">{{ t("setup.sent.title") }}</h2>
          <ul class="mt-1 list-disc space-y-1 pl-5 text-[1.05rem] text-papier">
            <li v-for="d in continuous" :key="d.id">{{ sent(d) }}</li>
          </ul>
        </div>
      </section>

      <!-- 3. Options, chosen while the required components download -->
      <section v-else-if="step === 'options'" class="space-y-6" aria-labelledby="etape-options">
        <h2 id="etape-options" class="text-[1.15rem] font-bold text-papier">{{ t("setup.options.title") }}</h2>
        <p class="-mt-3 text-[1rem] text-courbe">{{ t("setup.options.intro") }}</p>

        <div class="space-y-1">
          <label for="cle" class="block text-[1.15rem] font-bold text-papier">{{ t("setup.key.label") }} <span class="text-[1rem] text-courbe">{{ t("setup.key.recommended") }}</span></label>
          <input id="cle" v-model="key" type="password" autocomplete="off" spellcheck="false" placeholder="nvapi-…"
                 :aria-invalid="!!keyError" aria-describedby="cle-aide"
                 class="w-full rounded-md border bg-relief px-3 py-2.5 text-papier"
                 :class="keyError ? 'border-alerte' : 'border-courbe-fonce'" />
          <p v-if="keyError" class="text-[1rem] text-alerte" role="alert">{{ keyError }}</p>
          <label v-if="!key.trim()" class="flex items-start gap-3 text-[1.05rem]">
            <input v-model="noKey" type="checkbox" :class="check" />
            <span class="text-papier">{{ t("setup.no_key") }}
              <span class="block text-[1rem] text-courbe">{{ t("setup.no_key.detail") }}</span>
            </span>
          </label>
          <p id="cle-aide" class="text-[1rem] text-courbe">
            {{ t("setup.key.help") }}
          </p>
        </div>

        <fieldset class="space-y-2">
          <legend class="mb-2 text-[1.15rem] font-bold text-papier">{{ t("setup.components") }}</legend>
          <label v-for="o in OPTIONS" :key="o.id" class="flex items-start gap-3 text-[1.05rem]">
            <input v-model="chosen[o.id]" type="checkbox" :class="check" />
            <span>
              <span class="text-papier">{{ t(`setup.option.${o.id}`) }}</span>
              <span v-if="o.recommended" class="text-courbe">{{ t("setup.recommended") }}</span>
              <span class="block text-[1rem] text-courbe">{{ t(`setup.option.${o.id}.detail`) }}</span>
            </span>
          </label>
          <label class="flex items-start gap-3 text-[1.05rem]">
            <input v-model="shortcuts" type="checkbox" :class="check" />
            <span>
              <span class="text-papier">{{ t("setup.shortcuts") }}</span><span class="text-courbe">{{ t("setup.recommended") }}</span>
              <span class="block text-[1rem] text-courbe">{{ t("setup.shortcuts.detail") }}</span>
            </span>
          </label>
        </fieldset>

        <fieldset class="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
          <legend class="mb-2 text-[1.15rem] font-bold text-papier">{{ t("setup.default_level") }}</legend>
          <label v-for="l in LEVELS" :key="l" class="flex items-start gap-3 text-[1.05rem]">
            <input v-model="helpLevel" type="radio" :class="check" name="niveau" :value="l" />
            <span>
              <span class="text-papier">{{ l }}. {{ t(`level.${l}`) }}</span>
              <span class="block text-[1rem] text-courbe">{{ t(`level.${l}.hint`) }}</span>
            </span>
          </label>
        </fieldset>
      </section>

      <!-- 4. Installation: progress, then the first start -->
      <section v-else class="space-y-4" aria-labelledby="etape-installation">
        <h2 id="etape-installation" class="text-[1.15rem] font-bold text-papier">{{ t("setup.install.title") }}</h2>
        <ol role="status" aria-live="polite" class="space-y-2">
          <li v-for="(p, i) in PHASES" :key="p" class="flex items-center gap-3">
            <span class="grid h-6 w-6 place-items-center rounded-full text-[0.85rem] font-bold"
                  :class="i < phaseIndex ? 'bg-foret text-encre'
                    : i === phaseIndex && installDone === false ? 'bg-alerte text-encre'
                    : i === phaseIndex ? 'border-2 border-papier border-t-transparent animate-spin'
                    : 'border border-courbe-fonce'">
              {{ i < phaseIndex ? "✓" : i === phaseIndex && installDone === false ? "!" : "" }}
            </span>
            <span :class="i <= phaseIndex ? 'text-papier' : 'text-courbe'">{{ t(`setup.phase.${p}`) }}</span>
          </li>
        </ol>
        <p v-if="installDone === true" class="font-bold text-foret">{{ t("setup.install.done") }}</p>
        <div v-else-if="installDone === false" role="alert">
          <p class="font-bold text-alerte">{{ t("setup.install.failed") }}</p>
          <p v-if="failure" class="mt-1 text-[1.05rem] text-papier">{{ failure }}</p>
        </div>
        <details v-if="lines.length" :open="installDone === false">
          <summary :class="disclosure">{{ t("setup.install.log") }}</summary>
          <div ref="logBox" class="mt-2 max-h-48 overflow-auto rounded-md border border-courbe-fonce bg-relief px-3 py-2">
            <p v-for="(l, i) in lines" :key="i" class="whitespace-pre font-mono text-[0.95rem] leading-relaxed text-courbe">{{ l }}</p>
          </div>
        </details>
        <p v-if="installDone === true" class="text-[1.05rem] text-courbe">
          {{ t("setup.install.share") }}
        </p>
        <p v-if="finishError" class="text-[1.05rem] text-alerte" role="alert">{{ finishError }}</p>
      </section>
    </div>

    <footer v-if="status" class="flex items-center justify-end gap-2 border-t border-courbe-fonce px-6 py-3">
      <p v-if="step === 'components' && !installing" class="mr-auto text-[1rem] text-courbe">
        {{ t("setup.footer.download_next", { size: mb(requiredMb) }) }}
      </p>
      <template v-if="step === 'system'">
        <button v-if="missing.length" type="button" :class="secondary" @click="step = 'components'">{{ t("setup.skip") }}</button>
        <button v-if="missing.length" type="button" :class="primary" @click="load">{{ t("setup.recheck") }}</button>
        <button v-else type="button" :class="primary" @click="step = 'components'">{{ t("setup.next") }}</button>
      </template>
      <template v-else-if="step === 'components'">
        <button type="button" :class="secondary" @click="step = 'system'">{{ t("setup.back") }}</button>
        <button type="button" :class="primary" @click="installing ? (step = 'options') : startInstall()">{{ t("setup.next") }}</button>
      </template>
      <template v-else-if="step === 'options'">
        <button type="button" :class="secondary" @click="step = 'components'">{{ t("setup.back") }}</button>
        <button type="button" :class="primary" :disabled="!optionsValid" @click="step = 'install'"
                :title="optionsValid ? '' : t('setup.options_invalid')">{{ t("setup.next") }}</button>
      </template>
      <template v-else>
        <button type="button" :class="secondary" @click="step = 'options'">{{ t("setup.back") }}</button>
        <button v-if="installDone === false" type="button" :class="primary" @click="startInstall">{{ t("setup.retry") }}</button>
        <button v-else type="button" :class="primary" :disabled="installDone !== true || finishing" @click="finish">
          {{ t(finishing ? "setup.starting" : "setup.launch") }}
        </button>
      </template>
    </footer>
  </main>
</template>
