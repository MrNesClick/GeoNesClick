<script setup lang="ts">
// Assistant de premier lancement (AppImage), décidé avec l'utilisateur le 2026-11-07 :
// - par ÉTAPES, l'obligatoire d'abord ;
// - 100 % transparent : TOUT ce qui sera téléchargé (quoi, d'où, taille, licence, quand, ce qui part de ta machine)
//   s'affiche AVANT le moindre octet, paquet par paquet si tu le veux ; un accord pour le bloc obligatoire, puis
//   chaque option a son Valider / Passer, avec ma recommandation précochée ;
// - les gros téléchargements tournent pendant que tu choisis tes options ; celles-ci sont écrites AVANT le premier
//   démarrage du moteur (il ne télécharge jamais une option refusée). Tout reste modifiable dans les Réglages.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { fr } from "../engine";

interface Download {
  id: string; what: string; hosts: string[]; size_mb: number; license: string; why: string;
  when: "installation" | "option" | "demande" | "continu"; required: boolean; option?: string; sends?: string;
}
interface Package { name: string; version: string; size: number; license: string; note?: string }
interface Check { label: string; ok: boolean; package: string }
interface Status {
  bundled: boolean; needed: boolean; version: string | null; installed: string | null; gpu: boolean;
  checks: Check[]; downloads: { download: Download[] }; packages_cuda: Package[]; packages_cpu: Package[];
}

const emit = defineEmits<{ done: [] }>();
const status = ref<Status | null>(null);
const step = ref<"system" | "downloads" | "options" | "finish">("system");
const variant = ref<"cuda" | "cpu">("cpu");
const showPackages = ref(false);
let invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

async function load() {
  ({ invoke } = await import("@tauri-apps/api/core"));
  status.value = (await invoke("setup_status")) as Status;
  variant.value = status.value.gpu ? "cuda" : "cpu";
  if (status.value.checks.every((c) => c.ok)) step.value = "downloads";
}

// --- liste des téléchargements ---------------------------------------------------------------------
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
const mb = (n: number) => (n >= 1000 ? `${fr(n / 1000)} Go` : n >= 1 ? `${Math.round(n)} Mo` : n ? "< 1 Mo" : "—");
const WHEN: Record<Download["when"], string> = {
  installation: "une fois, maintenant", option: "une fois, si tu l'acceptes", demande: "au fil de l'usage, si utile",
  continu: "à chaque usage",
};
const missing = computed(() => (status.value?.checks ?? []).filter((c) => !c.ok));
const aptCommand = computed(() => `sudo apt install ${missing.value.map((c) => c.package).join(" ")}`);

// --- installation (en fond) ------------------------------------------------------------------------
const phase = ref("");
const bytes = ref(0);
const lines = ref<string[]>([]);
const installDone = ref<boolean | null>(null); // null : en cours ; true / false : terminé
const installing = ref(false);
const PHASES: Record<string, string> = {
  python: "Python 3.12", paquets: "Bibliothèques du moteur", moteur: "Moteur GeoNesClick", modele: "Modèle StreetCLIP",
  finition: "Mise en place", fini: "Terminé",
};
let unlisten: (() => void) | null = null;
async function startInstall() {
  const { listen } = await import("@tauri-apps/api/event");
  unlisten = await listen<{ phase: string | null; line: string | null; bytes: number | null; done: boolean; ok: boolean }>(
    "setup-progress", ({ payload: p }) => {
      if (p.phase) phase.value = p.phase;
      if (p.bytes !== null) bytes.value = p.bytes;
      if (p.line && !p.line.startsWith("PHASE ")) lines.value = [...lines.value.slice(-5), p.line];
      if (p.done) installDone.value = p.ok;
    });
  installing.value = true;
  step.value = "options";
  try {
    await invoke("setup_install", { variant: variant.value });
  } catch (e) {
    installDone.value = false;
    lines.value = [...lines.value, String(e)];
  }
}
const percent = computed(() => Math.min(99, Math.round((bytes.value / 1e6 / Math.max(1, requiredMb.value)) * 100)));
onBeforeUnmount(() => unlisten?.());

// --- options : Valider / Passer, recommandation précochée ------------------------------------------
interface Option { id: string; label: string; detail: string; download?: string; recommended: boolean; settings: Record<string, Record<string, unknown>> }
const OPTIONS: Option[] = [
  { id: "places", label: "Noms de lieux (GeoNames)", recommended: true, download: "geonames",
    detail: "Reconnaît les villes lues sur tes marques et leurs régions. Puis, à la demande, les villages du pays en tête.",
    settings: { rules: { places: true, detail: true } } },
  { id: "plonkit", label: "Guides Plonk It", recommended: true, download: "plonkit",
    detail: "Astuces par pays qui ressemblent à ta vue. Traduites par l'IA si tu donnes ta clé (traduction d'avance comprise).",
    settings: { plonkit: { enabled: true } } },
  { id: "map", label: "Carte (fond OpenStreetMap)", recommended: true, download: "tiles",
    detail: "Onglet Carte : pays, lieux lus, position estimée. Le serveur de tuiles voit ton adresse IP et les zones vues.",
    settings: { map: { enabled: true } } },
  { id: "plonk", label: "Zones probables sur la carte (PLONK)", recommended: false, download: "plonk",
    detail: "Calculées en local, ~120 Mo de mémoire vidéo de plus. Une piste, pas une preuve.",
    settings: { plonk: { enabled: true } } },
];
const OFF: Record<string, Record<string, Record<string, unknown>>> = {
  places: { rules: { places: false, detail: false } }, plonkit: { plonkit: { enabled: false } },
  map: { map: { enabled: false } }, plonk: { plonk: { enabled: false } },
};
const chosen = ref<Record<string, boolean>>(Object.fromEntries(OPTIONS.map((o) => [o.id, o.recommended])));
const key = ref("");
const useKey = ref(true);
const shortcuts = ref(true);
const helpLevel = ref(4);
const LEVELS = [
  { value: 1, label: "Regarder", hint: "où regarder, sans nommer de pays" },
  { value: 2, label: "Indices", hint: "plus ce que voit l'IA" },
  { value: 3, label: "Pays", hint: "plus les pays probables, la carte, les astuces" },
  { value: 4, label: "Réponse", hint: "plus la synthèse : pays, région, preuve" },
];
const choices = computed(() => {
  const out: Record<string, Record<string, unknown>> = { coach: { help_level: helpLevel.value } };
  for (const o of OPTIONS) {
    for (const [section, values] of Object.entries(chosen.value[o.id] ? o.settings : OFF[o.id])) {
      out[section] = { ...(out[section] ?? {}), ...values };
    }
  }
  if (!(useKey.value && key.value.trim())) out.plonkit = { ...(out.plonkit ?? {}), pretranslate: false };
  return out;
});

// --- fin : options écrites, raccourcis, premier démarrage -------------------------------------------
const finishing = ref(false);
const finishError = ref("");
async function finish() {
  finishing.value = true;
  finishError.value = "";
  try {
    await invoke("setup_apply", { choices: choices.value, apiKey: useKey.value ? key.value : null });
    if (shortcuts.value) {
      await invoke("setup_shortcuts").catch((e) => (finishError.value = `Raccourcis non installés : ${e}`));
    }
    await invoke("restart_engine");
    emit("done");
  } catch (e) {
    finishError.value = String(e);
  } finally {
    finishing.value = false;
  }
}

onMounted(load);

const box = "rounded-md border border-courbe-fonce px-3 py-2";
const primary = "rounded-md bg-papier px-4 py-2 font-bold text-encre hover:bg-white disabled:opacity-40";
const secondary = "rounded-md border border-courbe-fonce px-3 py-1.5 text-papier hover:bg-relief disabled:opacity-40";
</script>

<template>
  <main class="mx-auto max-w-2xl px-4 py-6">
    <h1 class="atlas text-[1.8rem] text-papier">GeoNesClick — premiers pas</h1>
    <p v-if="status?.installed && status.installed !== status.version" class="mt-1 text-courbe">
      Mise à jour du moteur : version {{ status.installed }} → {{ status.version }}.
    </p>
    <p v-if="!status" class="mt-4 text-courbe">Vérification…</p>

    <!-- 1. Système -->
    <section v-else-if="step === 'system'" class="mt-4 space-y-3" aria-labelledby="etape-systeme">
      <h2 id="etape-systeme" class="font-bold text-papier">1. Ton système</h2>
      <p class="text-courbe">La capture de la fenêtre du jeu passe par des composants de GNOME, présents d'habitude.</p>
      <ul :class="box" class="space-y-1">
        <li v-for="c in status.checks" :key="c.label" class="flex gap-2">
          <span :class="c.ok ? 'text-foret' : 'text-alerte'">{{ c.ok ? "✔" : "✘" }}</span>
          <span class="flex-1 text-papier">{{ c.label }}</span>
          <code v-if="!c.ok" class="text-courbe">{{ c.package }}</code>
        </li>
      </ul>
      <div v-if="missing.length" class="space-y-2">
        <p class="text-papier">Il en manque : installe-les avec cette commande (dans un terminal), puis revérifie.</p>
        <code class="block rounded bg-relief px-3 py-2 text-papier select-all">{{ aptCommand }}</code>
        <div class="flex flex-wrap gap-2">
          <button type="button" :class="primary" @click="load">Revérifier</button>
          <button type="button" :class="secondary" @click="step = 'downloads'">Continuer sans (la capture ne marchera pas)</button>
        </div>
      </div>
    </section>

    <!-- 2. Tout ce qui sera téléchargé -->
    <section v-else-if="step === 'downloads'" class="mt-4 space-y-4" aria-labelledby="etape-telechargements">
      <h2 id="etape-telechargements" class="font-bold text-papier">2. Ce que GeoNesClick va télécharger</h2>
      <p class="text-courbe">Rien n'a encore été téléchargé. Voici tout, avant ton accord.</p>

      <div :class="box">
        <p class="font-bold text-papier">Obligatoire, une fois · {{ mb(requiredMb) }}</p>
        <p class="text-[0.85rem] text-courbe">Sans cela l'application ne fait rien. Installé dans ~/.local/share/geonesclick/engine, rien dans ton système.</p>
        <label v-if="status.gpu" class="mt-2 flex items-start gap-2 text-[0.9rem] text-papier">
          <input type="checkbox" :checked="variant === 'cpu'" @change="variant = variant === 'cpu' ? 'cuda' : 'cpu'" />
          <span>Carte NVIDIA détectée : PyTorch CUDA (rapide). Cocher pour la version processeur, plus légère et plus lente.</span>
        </label>
        <p v-else class="mt-2 text-[0.85rem] text-courbe">Pas de carte NVIDIA : version processeur de PyTorch (plus lente).</p>
        <table class="mt-2 w-full text-[0.85rem]">
          <tbody>
            <tr v-for="d in required" :key="d.id" class="border-t border-courbe-fonce/50 align-top">
              <td class="py-1 pr-2 text-papier">{{ d.what }}<span class="block text-courbe">{{ d.why }}</span></td>
              <td class="py-1 pr-2 text-courbe">{{ d.hosts.join(", ") }}<span class="block">{{ d.license }}</span></td>
              <td class="py-1 text-right tabular-nums text-papier">{{ d.id === "pytorch-cpu" ? "inclus" : mb(sizeOf(d)) }}</td>
            </tr>
          </tbody>
        </table>
        <button type="button" class="mt-2 text-[0.85rem] text-courbe underline underline-offset-2 hover:text-papier"
                @click="showPackages = !showPackages">
          {{ showPackages ? "Masquer" : "Voir" }} les {{ packages.length }} paquets, un par un
        </button>
        <table v-if="showPackages" class="mt-1 w-full text-[0.8rem]">
          <tbody>
            <tr v-for="p in packages" :key="p.name" class="border-t border-courbe-fonce/40">
              <td class="py-0.5 pr-2 text-papier">{{ p.name }} {{ p.version }}</td>
              <td class="py-0.5 pr-2 text-courbe">{{ p.license }}</td>
              <td class="py-0.5 text-right tabular-nums text-courbe">{{ p.note ? p.note : mb(p.size / 1e6) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div :class="box">
        <p class="font-bold text-papier">Options : tu choisiras chacune à l'étape suivante</p>
        <ul class="mt-1 space-y-1 text-[0.85rem]">
          <li v-for="d in all.filter((x) => x.when === 'option' || x.when === 'demande')" :key="d.id">
            <span class="text-papier">{{ d.what }}</span>
            <span class="text-courbe"> · {{ d.hosts.join(", ") }} · {{ mb(d.size_mb) }} · {{ WHEN[d.when] }} · {{ d.license }}</span>
          </li>
        </ul>
      </div>

      <div :class="box">
        <p class="font-bold text-papier">En continu, si tu les actives</p>
        <ul class="mt-1 space-y-1 text-[0.85rem]">
          <li v-for="d in all.filter((x) => x.when === 'continu')" :key="d.id">
            <span class="text-papier">{{ d.what }}</span> <span class="text-courbe">· {{ d.hosts.join(", ") }}</span>
            <span class="block text-alerte">Part de ta machine : {{ d.sends }}</span>
          </li>
        </ul>
      </div>

      <button type="button" :class="primary" @click="startInstall">
        Je comprends, télécharger l'obligatoire ({{ mb(requiredMb) }})
      </button>
    </section>

    <!-- 3. Options pendant l'installation -->
    <section v-else class="mt-4 space-y-4" aria-labelledby="etape-options">
      <div :class="box" role="status" aria-live="polite">
        <p class="text-papier">
          <template v-if="installDone === true">Moteur installé ✔</template>
          <template v-else-if="installDone === false"><span class="text-alerte">Installation interrompue.</span></template>
          <template v-else>{{ PHASES[phase] ?? "Préparation" }}… {{ mb(bytes / 1e6) }} / ~{{ mb(requiredMb) }}</template>
        </p>
        <div v-if="installDone === null" class="mt-1 h-1.5 rounded-full bg-courbe-fonce">
          <div class="h-full rounded-full bg-foret" :style="{ width: `${percent}%` }" />
        </div>
        <p v-for="(l, i) in lines" :key="i" class="truncate text-[0.75rem] text-courbe">{{ l }}</p>
        <button v-if="installDone === false" type="button" :class="secondary" class="mt-2" @click="startInstall">Réessayer</button>
      </div>

      <h2 id="etape-options" class="font-bold text-papier">3. Tes options (pendant le téléchargement)</h2>

      <div :class="box" class="space-y-2">
        <p class="text-papier">Clé API NVIDIA <span class="text-[0.85rem] text-foret">★ recommandée</span></p>
        <p class="text-[0.85rem] text-courbe">
          Gratuite sur build.nvidia.com (« Get API Key »). Sans elle : pas d'analyse approfondie ni de lecture des marques.
          {{ byId("nvidia")?.sends ? `Avec elle, part vers ${byId("nvidia")?.hosts[0]} : ${byId("nvidia")?.sends}.` : "" }}
          Rangée dans ~/.config/geonesclick/nvapi.key, lisible par toi seul.
        </p>
        <input v-model="key" type="password" autocomplete="off" spellcheck="false" :disabled="!useKey" placeholder="nvapi-…"
               class="w-full rounded-md border border-courbe-fonce bg-relief px-3 py-1.5 text-papier" />
        <div class="flex gap-2">
          <button type="button" :class="useKey ? primary : secondary" @click="useKey = true">Valider</button>
          <button type="button" :class="!useKey ? primary : secondary" @click="useKey = false">Passer</button>
        </div>
      </div>

      <div v-for="o in OPTIONS" :key="o.id" :class="box" class="space-y-1">
        <p class="text-papier">{{ o.label }} <span v-if="o.recommended" class="text-[0.85rem] text-foret">★ recommandée</span></p>
        <p class="text-[0.85rem] text-courbe">{{ o.detail }}</p>
        <p v-if="o.download && byId(o.download)" class="text-[0.8rem] text-courbe">
          {{ byId(o.download)!.hosts.join(", ") }} · {{ mb(byId(o.download)!.size_mb) }} · {{ WHEN[byId(o.download)!.when] }} ·
          {{ byId(o.download)!.license }}
        </p>
        <div class="flex gap-2">
          <button type="button" :class="chosen[o.id] ? primary : secondary" @click="chosen[o.id] = true">Valider</button>
          <button type="button" :class="!chosen[o.id] ? primary : secondary" @click="chosen[o.id] = false">Passer</button>
        </div>
      </div>

      <div :class="box" class="space-y-1">
        <p class="text-papier">Raccourcis clavier GNOME <span class="text-[0.85rem] text-foret">★ recommandés</span></p>
        <p class="text-[0.85rem] text-courbe">Super+Maj+G pour capturer, Super+Maj+Z pour marquer, depuis le jeu. Sinon : les boutons de l'app.</p>
        <div class="flex gap-2">
          <button type="button" :class="shortcuts ? primary : secondary" @click="shortcuts = true">Valider</button>
          <button type="button" :class="!shortcuts ? primary : secondary" @click="shortcuts = false">Passer</button>
        </div>
      </div>

      <fieldset :class="box">
        <legend class="px-1 text-papier">Niveau d'aide au départ</legend>
        <label v-for="l in LEVELS" :key="l.value" class="flex items-baseline gap-2 text-[0.9rem]">
          <input v-model="helpLevel" type="radio" name="niveau" :value="l.value" />
          <span class="text-papier">{{ l.value }}. {{ l.label }}</span><span class="text-courbe">— {{ l.hint }}</span>
        </label>
      </fieldset>

      <div class="space-y-2">
        <button type="button" :class="primary" :disabled="installDone !== true || finishing" @click="finish">
          {{ finishing ? "Démarrage…" : installDone === true ? "Terminer et démarrer" : "Terminer (après le téléchargement)" }}
        </button>
        <p class="text-[0.85rem] text-courbe">
          Au démarrage, GNOME te demandera quelle fenêtre partager : choisis celle du jeu. Tout se change ensuite dans les Réglages.
        </p>
        <p v-if="finishError" class="text-[0.85rem] text-alerte" role="alert">{{ finishError }}</p>
      </div>
    </section>
  </main>
</template>
