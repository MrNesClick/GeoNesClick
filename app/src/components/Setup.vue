<script setup lang="ts">
// First-launch assistant (AppImage):
// - in STEPS, the required part first;
// - 100 % transparent: EVERYTHING that will be downloaded (what, from where, size, licence, when, what leaves your
//   machine) is shown BEFORE a single byte, package by package if you want; one consent for the required block,
//   then each option has its Accept / Skip, with my recommendation pre-ticked;
// - the big downloads run while you choose your options; these are written BEFORE the engine's first
//   start (it never downloads a declined option). Everything stays editable in the Settings.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { num } from "../engine";
import { hasKey, i18n, LANGS, setLanguage, t, uiLanguage, type Key, type Lang } from "../i18n";
import WhatsNew, { type Release } from "./WhatsNew.vue";

// Language: English by default, chosen on the first screen, written to
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
  /** setup.rs, package_manager: the command to show and the Install button; none when unknown. */
  package_manager: "apt" | "dnf" | "pacman" | "zypper" | null;
  /** Where the engine and the models go, home written ~ (XDG_DATA_HOME, HF_HOME… followed). */
  data_dir: string; models_dir: string;
  /** Another version installed with its choices: updated without a question. */
  upgrade: boolean;
  /** This AppImage is older than the installed version: nothing is touched. */
  older: boolean;
  installed_variant: "cuda" | "cpu" | null;
  /** The installed copy of the application (setup.rs, installed_appimage) exists; copy_dir: its folder, as shown. */
  installed_copy: boolean; copy_dir: string;
  /** For an update: the CHANGELOG sections since the installed version, newest first. */
  whats_new: Release[];
  /** For an update: the libraries it would download (setup.rs, update_fetches); empty when only GeoNesClick changes. */
  update_fetches: { name: string; version: string; size: number }[];
}

const emit = defineEmits<{ done: [] }>();
const status = ref<Status | null>(null);
const step = ref<"system" | "components" | "options" | "install">("system");
const STEPS = ["system", "components", "options", "install"] as const;
const stepIndex = computed(() => STEPS.indexOf(step.value));
const variant = ref<"cuda" | "cpu">("cpu");
const showPackages = ref(false);
let invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
/** setup: the first installation's steps; update: a newer version over an installed one, without a question; older:
 * an older AppImage than the installed version, which touches nothing. */
const mode = computed(() => (status.value?.older ? "older" : status.value?.upgrade ? "update" : "setup"));

async function load() {
  ({ invoke } = await import("@tauri-apps/api/core"));
  status.value = (await invoke("setup_status")) as Status;
  variant.value = status.value.gpu ? "cuda" : "cpu";
  if (mode.value === "older") return;
  if (mode.value === "update") {
    variant.value = status.value.installed_variant ?? variant.value; // the same engine, updated
    if (updateAccepted.value && status.value.checks.every((c) => c.ok) && !installing.value) startInstall();
    return;
  }
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
/** A note of the package list (bundle_meta.py): an id with its text in the catalogs, shown as is otherwise. */
const packageNote = (note: string) => {
  const key = `setup.package_note.${note}`;
  return hasKey(key) ? t(key) : note;
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
const INSTALL = {
  apt: "sudo apt install", dnf: "sudo dnf install", pacman: "sudo pacman -S --needed", zypper: "sudo zypper install",
} as const;
const packageManager = computed(() => status.value?.package_manager ?? null);
// No command for an unknown package manager: the packages' names (Debian's) are only a hint there.
const installCommand = computed(() =>
  packageManager.value ? `${INSTALL[packageManager.value]} ${missing.value.map((c) => c.package).join(" ")}` : "");
const missingText = computed(() => t(packageManager.value ? "setup.system.missing" : "setup.system.missing_unknown"));
// The missing packages installed from here (setup.rs, setup_system_install: pkexec + apt-get), then checked again.
const systemInstalling = ref(false);
const systemError = ref("");
async function installSystem() {
  systemInstalling.value = true;
  systemError.value = "";
  try {
    await invoke("setup_system_install");
    await load();
  } catch (e) {
    systemError.value = String(e);
  } finally {
    systemInstalling.value = false;
  }
}

// --- installation (in the background) --------------------------------------------------------------
const phase = ref("");
const lines = ref<string[]>([]);
const installDone = ref<boolean | null>(null); // null: running; true / false: finished
const failure = ref(""); // likely cause of a failure (site down, disk full), from setup.rs; empty: see the log
const installing = ref(false);
// Phases announced by install-engine.sh ("PHASE <name>"), in order.
const PHASES = ["python", "packages", "engine", "model", "finish"] as const;
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
interface Option { id: "places" | "plonkit" | "map" | "plonk" | "updates"; recommended: boolean; settings: Record<string, Record<string, unknown>> }
const OPTIONS: Option[] = [
  { id: "places", recommended: true, settings: { rules: { places: true, detail: true } } },
  { id: "plonkit", recommended: true, settings: { plonkit: { enabled: true } } },
  { id: "map", recommended: true, settings: { map: { enabled: true } } },
  { id: "plonk", recommended: false, settings: { plonk: { enabled: true } } },
  { id: "updates", recommended: true, settings: { updates: { check: true } } },
];
const OFF: Record<string, Record<string, Record<string, unknown>>> = {
  places: { rules: { places: false, detail: false } }, plonkit: { plonkit: { enabled: false } },
  map: { map: { enabled: false } }, plonk: { plonk: { enabled: false } }, updates: { updates: { check: false } },
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
// Off unless chosen: the entry is written outside the app's folders (~/.local/share/applications).
const menu = ref(false);
const helpLevel = ref(4);
// Choices survive a closed window (the API key never: it is a secret); forgotten once the installation is done.
const SAVED = "geonesclick.setup";
function restoreChoices() {
  try {
    const saved = JSON.parse(localStorage.getItem(SAVED) ?? "null");
    if (!saved) return;
    Object.assign(chosen.value, saved.chosen ?? {});
    if (typeof saved.shortcuts === "boolean") shortcuts.value = saved.shortcuts;
    if (typeof saved.menu === "boolean") menu.value = saved.menu;
    if (typeof saved.helpLevel === "number") helpLevel.value = saved.helpLevel;
    if (typeof saved.noKey === "boolean") noKey.value = saved.noKey;
    if (saved.variant === "cuda" || saved.variant === "cpu") variant.value = saved.variant;
    if (typeof saved.language === "string") chooseLanguage(saved.language);
  } catch {
    /* storage unavailable or damaged: the recommended choices stay */
  }
}
watch(
  () => ({ chosen: chosen.value, shortcuts: shortcuts.value, menu: menu.value, helpLevel: helpLevel.value, noKey: noKey.value, variant: variant.value,
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
/** The options are applied but the shortcuts or the menu entry failed: the error stays shown until "Launch anyway". */
const integrationFailed = ref(false);
// Back to the options: the choices may change, so the next launch applies them and tries again.
watch(step, () => {
  integrationFailed.value = false;
  finishError.value = "";
});
async function finish() {
  finishing.value = true;
  try {
    if (!integrationFailed.value) {
      finishError.value = "";
      await invoke("setup_apply", { choices: choices.value, apiKey: key.value.trim() || null });
      const failed: string[] = [];
      // Before the menu entry: it points to the copy.
      await placeApp().catch((e) => failed.push(String(e)));
      if (shortcuts.value) {
        await invoke("set_shortcuts", { on: true }).catch((e) => failed.push(t("setup.shortcuts_failed", { error: String(e) })));
      }
      if (menu.value) {
        await invoke("set_menu_entry", { on: true }).catch((e) => failed.push(t("setup.menu_failed", { error: String(e) })));
      }
      if (failed.length) {
        finishError.value = [...failed, t("setup.integration_later")].join(" ");
        integrationFailed.value = true;
        return;
      }
    }
    await invoke("restart_engine");
    try {
      localStorage.setItem("geonesclick.updates_told", "1"); // the update check was a choice here (Notices.vue)
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

/** What the coach says once after an installation or an update (Notices.vue): the downloaded file that can be deleted,
 * and for an update what changed. */
const NOTICE = "geonesclick.notice";
function notice(file: string | null) {
  const whatsNew = mode.value === "update" ? status.value?.whats_new ?? [] : [];
  if (!status.value || (!file && !whatsNew.length)) return;
  try {
    localStorage.setItem(NOTICE, JSON.stringify({ version: status.value.version, dir: status.value.copy_dir, file, whats_new: whatsNew }));
  } catch {
    /* storage unavailable: the note is simply not shown */
  }
}
/** The application copied to its folder (setup.rs, place_appimage); a failure is told by the caller, and the note
 * still says what an update brings. */
async function placeApp() {
  let file: string | null = null;
  try {
    file = (await invoke("place_appimage")) as string | null;
  } finally {
    notice(file);
  }
}

// --- update: the installed choices and key are kept, the coach starts as soon as the engine is updated -----
const updateError = ref("");
/** An update is asked first, every time: what changed and what it would download; "Later" keeps the installed one. */
const updateAccepted = ref(false);
const fetchMb = computed(() => (status.value?.update_fetches ?? []).reduce((n, f) => n + f.size, 0) / 1e6);
function acceptUpdate() {
  updateAccepted.value = true;
  if (status.value?.checks.every((c) => c.ok)) startInstall();
}
async function later() {
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().close(); // the installed version stays as it is
}
/** What the update does now, in one line: a library being downloaded is named with its size (uv: "Downloading torch
 * (199.8MiB)"), which tells why it takes time; otherwise only the version. */
const updateNow = computed(() => {
  const download = [...lines.value].reverse().map((l) => /^Downloading (\S+) \(([^)]+)\)/.exec(l.trim())).find(Boolean);
  if (download && installDone.value !== true && phase.value === "packages") {
    const size = /^([\d.]+)(KiB|MiB|GiB)$/.exec(download[2]);
    const megabytes = size ? Number(size[1]) * { KiB: 1 / 1024, MiB: 1, GiB: 1024 }[size[2] as "KiB" | "MiB" | "GiB"] : 0;
    return t("setup.update.downloading", { name: download[1], size: megabytes ? mb(megabytes) : download[2] });
  }
  return t("setup.update.now", { version: status.value?.version ?? "" });
});
const updateShare = computed(() => (installDone.value === true ? 100 : Math.max(5, Math.round((100 * Math.max(phaseIndex.value, 0)) / PHASES.length))));
watch(installDone, async (done) => {
  if (mode.value !== "update" || done !== true) return;
  try {
    await invoke("setup_finish_update");
    await placeApp().catch((e) => console.warn("[setup] copy", e)); // the old copy still runs: not a reason to stop
    await invoke("restart_engine");
    emit("done");
  } catch (e) {
    updateError.value = String(e);
  }
});
const openInstalled = () => invoke("open_installed").catch((e) => (updateError.value = String(e)));

onMounted(load);

const box = "rounded-md border border-courbe-fonce px-3 py-2";
const disclosure = "cursor-pointer select-none py-1 text-[1.05rem] text-papier underline-offset-4 hover:underline";
const primary = "rounded-md bg-papier px-6 py-2.5 text-[1.05rem] font-bold text-encre hover:bg-white disabled:opacity-40";
const secondary = "rounded-md border border-courbe-fonce px-5 py-2.5 text-[1.05rem] text-papier hover:bg-relief disabled:opacity-40";
const check = "mt-1 h-5 w-5 shrink-0 cursor-pointer accent-lac";
</script>

<template>
  <main v-if="status && mode === 'older'" class="flex h-screen flex-col justify-center gap-4 bg-encre px-6 text-[1.05rem]">
    <h1 class="text-[1.4rem] font-bold text-papier">{{ t("setup.older.title") }}</h1>
    <p class="text-papier">{{ t("setup.older.text", { installed: status.installed ?? "", version: status.version ?? "" }) }}</p>
    <button v-if="status.installed_copy" type="button" :class="primary" class="self-start" @click="openInstalled">
      {{ t("setup.older.open", { installed: status.installed ?? "" }) }}
    </button>
    <p v-if="updateError" class="text-alerte" role="alert">{{ updateError }}</p>
  </main>

  <main v-else-if="status && mode === 'update' && !updateAccepted" class="flex h-screen flex-col gap-4 bg-encre px-6 py-6 text-[1.05rem]">
    <h1 class="text-[1.4rem] font-bold text-papier">{{ t("setup.update.ask_title", { from: status.installed ?? "", to: status.version ?? "" }) }}</h1>
    <p class="text-courbe">{{ t("setup.update.intro") }}</p>
    <p v-if="!status.update_fetches.length" class="text-papier">{{ t("setup.update.nothing") }}</p>
    <details v-else>
      <summary :class="disclosure">{{ t("setup.update.download", { size: mb(fetchMb) }) }}</summary>
      <ul class="mt-2 max-h-40 overflow-y-auto pr-3 text-[0.95rem]">
        <li v-for="f in status.update_fetches" :key="f.name" class="flex justify-between gap-2 border-t border-courbe-fonce/50 py-0.5">
          <span class="text-papier">{{ f.name }} {{ f.version }}</span><span class="tabular-nums text-courbe">{{ mb(f.size / 1e6) }}</span>
        </li>
      </ul>
    </details>
    <WhatsNew v-if="status.whats_new.length" :releases="status.whats_new" :class="box" class="min-h-0 flex-1 overflow-y-auto pr-3" />
    <div class="mt-auto flex flex-wrap items-center justify-end gap-2">
      <span class="mr-auto text-[0.9rem] text-courbe">{{ t("setup.update.later_hint", { installed: status.installed ?? "" }) }}</span>
      <button type="button" :class="secondary" @click="later">{{ t("setup.update.later") }}</button>
      <button type="button" :class="primary" @click="acceptUpdate">{{ t("setup.update.go") }}</button>
    </div>
  </main>

  <main v-else-if="status && mode === 'update'" class="flex h-screen flex-col gap-4 bg-encre px-6 py-6 text-[1.05rem]">
    <h1 class="text-[1.4rem] font-bold text-papier">{{ t("setup.update.title", { from: status.installed ?? "", to: status.version ?? "" }) }}</h1>
    <p class="text-courbe">{{ t("setup.update.intro") }}</p>
    <div v-if="missing.length" class="space-y-2">
      <p class="text-papier">{{ missingText }}</p>
      <code v-if="installCommand" class="block rounded bg-relief px-3 py-2 text-papier select-all">{{ installCommand }}</code>
      <p v-if="systemError" class="text-alerte" role="alert">{{ systemError }}</p>
      <div class="flex gap-2">
        <button type="button" :class="secondary" :disabled="systemInstalling" @click="load">{{ t("setup.recheck") }}</button>
        <button v-if="packageManager" type="button" :class="primary" :disabled="systemInstalling" @click="installSystem">
          {{ systemInstalling ? t("setup.system.installing") : t("setup.system.install") }}
        </button>
      </div>
    </div>
    <!-- One line and a bar: the steps of an installation are only details here (an update copies the engine and
         downloads only what changed). What changed is offered by the coach afterwards (Notices.vue). -->
    <div v-else role="status" aria-live="polite" class="space-y-2">
      <p class="text-papier">{{ installDone === false ? t("setup.install.failed") : updateNow }}</p>
      <div class="h-2 overflow-hidden rounded-full bg-relief" aria-hidden="true">
        <div class="h-full rounded-full transition-[width] duration-500" :class="installDone === false ? 'bg-alerte' : 'bg-lac'"
             :style="{ width: `${updateShare}%` }" />
      </div>
    </div>
    <div v-if="installDone === false" role="alert">
      <p v-if="failure" class="text-papier">{{ failure }}</p>
      <button type="button" :class="primary" class="mt-3" @click="startInstall">{{ t("setup.retry") }}</button>
    </div>
    <p v-if="updateError" class="text-alerte" role="alert">{{ updateError }}</p>
    <details v-if="lines.length" :open="installDone === false">
      <summary :class="disclosure">{{ t("setup.update.details") }}</summary>
      <ol class="mt-2 space-y-1 text-[0.95rem]">
        <li v-for="(p, i) in PHASES" :key="p" :class="i <= phaseIndex ? 'text-papier' : 'text-courbe'">
          {{ i < phaseIndex ? "✓" : i === phaseIndex ? "…" : "·" }} {{ t(`setup.phase.${p}`) }}
        </li>
      </ol>
      <div ref="logBox" class="mt-2 max-h-48 overflow-auto rounded-md border border-courbe-fonce bg-relief px-3 py-2">
        <p v-for="(l, i) in lines" :key="i" class="whitespace-pre font-mono text-[0.95rem] leading-relaxed text-courbe">{{ l }}</p>
      </div>
    </details>
  </main>

  <main v-else class="flex h-screen flex-col bg-encre text-[1.05rem]">
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
      <section v-else-if="step === 'system'" class="space-y-4" aria-labelledby="step-system">
        <h2 id="step-system" class="text-[1.15rem] font-bold text-papier">{{ t("setup.system.title") }}</h2>
        <p class="text-[1.05rem] text-courbe">{{ t("setup.system.intro") }}</p>
        <ul :class="box" class="space-y-1">
          <li v-for="c in status.checks" :key="c.label" class="flex gap-2">
            <span :class="c.ok ? 'text-foret' : 'text-alerte'">{{ c.ok ? "✓" : "✗" }}</span>
            <span class="flex-1 text-papier">{{ t(c.label) }}</span>
            <code v-if="!c.ok" class="text-courbe">{{ c.package }}</code>
          </li>
        </ul>
        <div v-if="missing.length" class="space-y-2">
          <p class="text-papier">{{ missingText }}</p>
          <code v-if="installCommand" class="block rounded bg-relief px-3 py-2 text-papier select-all">{{ installCommand }}</code>
          <p v-if="systemError" class="text-alerte" role="alert">{{ systemError }}</p>
        </div>
      </section>

      <!-- 2. Components: a summary, the full list under the details -->
      <section v-else-if="step === 'components'" class="space-y-6" aria-labelledby="step-components">
        <div>
          <div class="flex items-baseline justify-between">
            <h2 id="step-components" class="text-[1.15rem] font-bold text-papier">{{ t("setup.required.title") }}</h2>
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
          <p class="mt-1 text-[1rem] text-courbe">{{ t("setup.where", { data: status.data_dir, models: status.models_dir }) }}</p>
          <p class="mt-1 text-[1rem] text-courbe">{{ t("setup.copy_note", { dir: status.copy_dir }) }}</p>
          <details class="mt-3">
            <summary :class="disclosure">{{ t("setup.sources") }}</summary>
            <table class="mt-2 w-full text-[1rem]">
              <tbody>
                <tr v-for="d in all" :key="d.id" class="border-t border-courbe-fonce/50 align-top">
                  <td class="py-1 pr-2 text-papier">{{ dl(d, "what") }}<span class="block text-courbe">{{ dl(d, "why") }}</span></td>
                  <td class="py-1 pr-2 text-courbe">{{ d.hosts.join(", ") }}<span class="block">{{ dl(d, "license") }} · {{ t(`setup.when.${d.when}`) }}</span></td>
                  <td class="py-1 text-right tabular-nums whitespace-nowrap text-papier">{{ d.id === "pytorch-cpu" ? t("setup.included") : mb(sizeOf(d)) }}</td>
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
                  <td class="py-0.5 text-right tabular-nums whitespace-nowrap text-courbe">{{ p.note ? packageNote(p.note) : mb(p.size / 1e6) }}</td>
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
      <section v-else-if="step === 'options'" class="space-y-6" aria-labelledby="step-options">
        <h2 id="step-options" class="text-[1.15rem] font-bold text-papier">{{ t("setup.options.title") }}</h2>
        <p class="-mt-3 text-[1rem] text-courbe">{{ t("setup.options.intro") }}</p>

        <div class="space-y-1">
          <label for="api-key" class="block text-[1.15rem] font-bold text-papier">{{ t("setup.key.label") }} <span class="text-[1rem] text-courbe">{{ t("setup.key.recommended") }}</span></label>
          <input id="api-key" v-model="key" type="password" autocomplete="off" spellcheck="false" placeholder="nvapi-…"
                 :aria-invalid="!!keyError" aria-describedby="api-key-help"
                 class="w-full rounded-md border bg-relief px-3 py-2.5 text-papier"
                 :class="keyError ? 'border-alerte' : 'border-courbe-fonce'" />
          <p v-if="keyError" class="text-[1rem] text-alerte" role="alert">{{ keyError }}</p>
          <label v-if="!key.trim()" class="flex items-start gap-3 text-[1.05rem]">
            <input v-model="noKey" type="checkbox" :class="check" />
            <span class="text-papier">{{ t("setup.no_key") }}
              <span class="block text-[1rem] text-courbe">{{ t("setup.no_key.detail") }}</span>
            </span>
          </label>
          <p id="api-key-help" class="text-[1rem] text-courbe">
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
          <label class="flex items-start gap-3 text-[1.05rem]">
            <input v-model="menu" type="checkbox" :class="check" />
            <span>
              <span class="text-papier">{{ t("setup.menu") }}</span>
              <span class="block text-[1rem] text-courbe">{{ t("setup.menu.detail") }}</span>
            </span>
          </label>
        </fieldset>

        <fieldset class="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
          <legend class="mb-2 text-[1.15rem] font-bold text-papier">{{ t("setup.default_level") }}</legend>
          <label v-for="l in LEVELS" :key="l" class="flex items-start gap-3 text-[1.05rem]">
            <input v-model="helpLevel" type="radio" :class="check" name="help-level" :value="l" />
            <span>
              <span class="text-papier">{{ l }}. {{ t(`level.${l}`) }}</span>
              <span class="block text-[1rem] text-courbe">{{ t(`level.${l}.hint`) }}</span>
            </span>
          </label>
        </fieldset>
      </section>

      <!-- 4. Installation: progress, then the first start -->
      <section v-else class="space-y-4" aria-labelledby="step-install">
        <h2 id="step-install" class="text-[1.15rem] font-bold text-papier">{{ t("setup.install.title") }}</h2>
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
        <button v-if="missing.length" type="button" :class="secondary" :disabled="systemInstalling"
                @click="step = 'components'">{{ t("setup.skip") }}</button>
        <button v-if="missing.length" type="button" :class="secondary" :disabled="systemInstalling" @click="load">{{ t("setup.recheck") }}</button>
        <button v-if="missing.length && packageManager" type="button" :class="primary" :disabled="systemInstalling"
                @click="installSystem">
          {{ systemInstalling ? t("setup.system.installing") : t("setup.system.install") }}
        </button>
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
          {{ t(finishing ? "setup.starting" : integrationFailed ? "setup.launch_anyway" : "setup.launch") }}
        </button>
      </template>
    </footer>
  </main>
</template>
