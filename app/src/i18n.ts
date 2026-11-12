// Texts the player sees, in their language: one catalog per language, shared with the engine (geonesclick/i18n.py)
// and the installer (src-tauri/src/i18n.rs). Same rules in the three layers: flat keys, "{name}" placeholders,
// English when a key or a language is missing.
import { reactive } from "vue";
import en from "../../engine/src/geonesclick/locales/en.json";

/** Every key of the English catalog, the reference: a typo is a type error. */
export type Key = keyof typeof en;
// Every locales/<lang>.json, found at build time: adding a language is adding its file.
const FILES = import.meta.glob<Record<string, string>>("../../engine/src/geonesclick/locales/*.json",
                                                         { eager: true, import: "default" });
const CATALOGS: Record<string, Record<string, string>> = Object.fromEntries(
  Object.entries(FILES).map(([path, texts]) => [path.split("/").pop()!.replace(/\.json$/, ""), texts]));
export type Lang = string;
export const LANGS: Lang[] = Object.keys(CATALOGS).sort((a, b) => (a === "en" ? -1 : b === "en" ? 1 : a.localeCompare(b)));

export const uiLanguage = (lang: unknown): Lang => (LANGS.includes(lang as Lang) ? (lang as Lang) : "en");
// The last language, remembered in this browser: the coach shows in it before the engine's state arrives.
const REMEMBERED = "geonesclick.lang";
function remembered(): Lang {
  try {
    return uiLanguage(localStorage.getItem(REMEMBERED));
  } catch {
    return "en"; // storage unavailable
  }
}
/** Language of the UI: coach.language when it has a catalog, English otherwise (es, de… translate the tips only). */
export const i18n = reactive({ lang: remembered() });
export function setLanguage(lang: unknown) {
  i18n.lang = uiLanguage(lang);
  document.documentElement.lang = i18n.lang;
  try {
    localStorage.setItem(REMEMBERED, i18n.lang);
  } catch {
    /* storage unavailable: English until the engine's state */
  }
  // The installer's own texts (errors, failure causes, GNOME shortcut names) follow too (src-tauri/src/i18n.rs).
  import("@tauri-apps/api/core")
    .then(({ invoke }) => invoke("set_language", { lang: i18n.lang }))
    .catch(() => {}); // outside Tauri (plain browser): nothing to tell
}

type Params = Record<string, string | number>;
const fill = (text: string, params?: Params) =>
  params ? text.replace(/\{(\w+)\}/g, (all, name: string) => (name in params ? String(params[name]) : all)) : text;

/** Is this a catalog key (keys built at run time, e.g. from a setting's name)? */
export const hasKey = (key: string): key is Key => key in en;

/** The text of a key in the UI's language (or in `lang`, e.g. each language's own name in the picker). */
export function t(key: Key, params?: Params, lang: Lang = i18n.lang): string {
  const texts: Record<string, string> = CATALOGS[lang];
  return fill(texts[key] ?? (en as Record<string, string>)[key] ?? key, params); // unknown key: shown as is
}

/** A value from the model's answer ("strong", "high"…: fixed English words of the prompt) in the UI's language:
 * the key `${prefix}.${value}` if the catalog has it, the value as is otherwise. */
export function valueLabel(prefix: string, value: string): string {
  const key = `${prefix}.${value.trim().toLowerCase()}`;
  return hasKey(key) ? t(key) : value;
}

/** An empty field of the model's answer ("" in the prompts' answer format; "unknown" for the driving side). */
export const isEmptyValue = (v: string) => ["", "unknown", "-"].includes(v.trim().toLowerCase().replace(/\.$/, ""));
/** The word "unreadable" in every catalog: the model writes it in the UI's language. */
export const unreadableWords = () => Object.values(CATALOGS).map((c) => (c["sum.unreadable"] ?? "").toLowerCase()).filter(Boolean);

/** Plural text: the key ".one" or ".other" (Intl.PluralRules, same as plural_one in i18n.py), with {n}. */
type PluralKey = Key extends infer K ? (K extends `${infer B}.one` ? B : never) : never;
export function tn(key: PluralKey, n: number, params?: Params): string {
  const form = new Intl.PluralRules(i18n.lang).select(n) === "one" ? "one" : "other";
  return t(`${key}.${form}` as Key, { n: num(n), ...params });
}

/** Number in the UI's language: "13.2" in English, "13,2" in French. */
export const num = (n: number, digits = 1) => n.toLocaleString(i18n.lang, { maximumFractionDigits: digits });
/** Share (0 to 1) as a whole percentage: "22%" in English, "22 %" in French. */
export const pct = (p: number) => p.toLocaleString(i18n.lang, { style: "percent", maximumFractionDigits: 0 });
/** Quoted text: “…” in English, « … » in French. */
export const quote = (text: string) => t("quote", { text });
/** Country name in the UI's language (Intl, no table to maintain). */
const regionNames: Partial<Record<Lang, Intl.DisplayNames>> = {};
export function countryName(code: string): string {
  regionNames[i18n.lang] ??= new Intl.DisplayNames([i18n.lang], { type: "region" });
  try {
    return regionNames[i18n.lang]!.of(code) ?? code;
  } catch {
    return code; // not a region code
  }
}
