// Description of the Settings screen: each editable engine setting (settings.py, EDITABLE) has its type and section
// here; the screen is built from this table. The texts come from the catalogs (i18n.ts), by keys derived from the
// setting: setting.<section>.<key> (label), .hint (help), .<value> and .<value>.hint (options); group.<id> (title);
// file.<section>.<key> (file-only settings).
import { hasKey, LANGS, t } from "./i18n";

export type Kind =
  | "bool"
  | "int"
  | "float"
  | "text"
  | "textarea"
  | "select"
  | "radio"
  | "rect" // [left, top, right, bottom] as fractions; empty = whole image
  | "rects" // list of rectangles, one per line
  | "categoryText" // one text value per metas category
  | "categoryNumber" // one number per category
  | "categoryList" // one list of words per category
  | "countries"; // candidate countries: tick, untick, add

export interface Field {
  section: string;
  key: string;
  kind: Kind;
  min?: number;
  max?: number;
  step?: number;
  /** Values offered (select, radio); their labels come from the catalog, or from `labels` when given. */
  options?: (string | number)[];
  /** Labels of the options that are not translated (each language in its own name). */
  labels?: Record<string, string>;
  /** Placed in the "Advanced" part of the section. */
  advanced?: boolean;
  /** Greyed out while this boolean setting is false. */
  needs?: [string, string];
}

export interface Group {
  id: string;
  /** Engine sections whose "file-only" part is shown in this group. */
  fileSections: string[];
  fields: Field[];
}

// The coach's language: en and fr (whole UI) in their own name; the others only translate the tips (hint in the
// option's label).
const LANGUAGES = ["en", "fr", "es", "de", "it", "pt"];
const OWN_NAMES = Object.fromEntries(LANGS.map((l) => [l, t("language.name", undefined, l)]));

const text = (key: string) => (hasKey(key) ? t(key) : "");
export const fieldLabel = (f: Field) => text(`setting.${f.section}.${f.key}`);
export const fieldHint = (f: Field) => text(`setting.${f.section}.${f.key}.hint`);
export const optionLabel = (f: Field, value: string | number) =>
  f.labels?.[String(value)] ?? text(`setting.${f.section}.${f.key}.${value}`);
export const optionHint = (f: Field, value: string | number) => text(`setting.${f.section}.${f.key}.${value}.hint`);
export const groupTitle = (g: Group) => text(`group.${g.id}`);
export const fileOnlyLabel = (id: string) => text(`file.${id}`) || id;

export const GROUPS: Group[] = [
  {
    id: "general",
    fileSections: [],
    fields: [
      { section: "coach", key: "help_level", kind: "radio", options: [1,2,3,4] },
      { section: "coach", key: "trust_proof", kind: "bool" },
      { section: "coach", key: "language", kind: "select", options: LANGUAGES, labels: OWN_NAMES },
      { section: "coach", key: "leader_min", kind: "float", min: 0, max: 1, step: 0.05, advanced: true },
      { section: "coach", key: "leader_margin", kind: "float", min: 0, max: 1, step: 0.05, advanced: true },
    ],
  },
  {
    id: "analysis",
    fileSections: ["streetclip","vision"],
    fields: [
      { section: "streetclip", key: "enabled", kind: "bool" },
      { section: "streetclip", key: "top_k", kind: "int", min: 1, max: 20 },
      { section: "streetclip", key: "countries", kind: "countries" },
      { section: "vision", key: "enabled", kind: "bool" },
      { section: "vision", key: "model", kind: "text", needs: ["vision", "enabled"] },
      { section: "vision", key: "thinking", kind: "bool", needs: ["vision", "enabled"] },
      { section: "vision", key: "timeout_s", kind: "float", min: 5, max: 300, needs: ["vision", "enabled"] },
      { section: "streetclip", key: "device", kind: "select", options: ["auto","cuda","cpu"], advanced: true },
      { section: "streetclip", key: "prompt", kind: "text", advanced: true },
      { section: "vision", key: "max_side_px", kind: "int", min: 256, max: 4096, advanced: true },
      { section: "vision", key: "max_tokens", kind: "int", min: 100, max: 16000, advanced: true },
      { section: "vision", key: "temperature", kind: "float", min: 0, max: 2, step: 0.1, advanced: true },
      { section: "vision", key: "prompt", kind: "textarea", advanced: true },
    ],
  },
  {
    id: "clues",
    fileSections: ["metas","plonkit"],
    fields: [
      { section: "metas", key: "enabled", kind: "bool" },
      { section: "metas", key: "include_seed", kind: "bool", needs: ["metas", "enabled"] },
      { section: "metas", key: "judge_buttons", kind: "bool", needs: ["metas", "include_seed"] },
      { section: "metas", key: "show_looks", kind: "bool", needs: ["metas", "enabled"] },
      { section: "metas", key: "max_categories", kind: "int", min: 1, max: 12, needs: ["metas", "enabled"] },
      { section: "plonkit", key: "enabled", kind: "bool" },
      { section: "plonkit", key: "similar_tips", kind: "bool", needs: ["plonkit", "enabled"] },
      { section: "plonkit", key: "similar_per_country", kind: "int", min: 1, max: 5, needs: ["plonkit", "enabled"] },
      { section: "plonkit", key: "translate", kind: "bool", needs: ["plonkit", "enabled"] },
      { section: "plonkit", key: "pretranslate", kind: "bool", needs: ["plonkit", "translate"] },
      { section: "plonkit", key: "translate_timeout_s", kind: "float", min: 5, max: 120, advanced: true, needs: ["plonkit", "translate"] },
      { section: "plonkit", key: "ai_classify", kind: "bool", needs: ["plonkit", "enabled"] },
      { section: "plonkit", key: "refresh_days", kind: "int", min: 1, max: 365, needs: ["plonkit", "enabled"] },
      { section: "metas", key: "min_probability", kind: "float", min: 0, max: 1, step: 0.01, advanced: true },
      { section: "metas", key: "max_candidates", kind: "int", min: 2, max: 20, advanced: true },
      { section: "metas", key: "max_looks", kind: "int", min: 1, max: 5, advanced: true },
      { section: "metas", key: "category_looks", kind: "categoryText", advanced: true },
      { section: "metas", key: "category_weights", kind: "categoryNumber", advanced: true },
      { section: "plonkit", key: "delay_s", kind: "float", min: 1, max: 60, advanced: true },
      { section: "plonkit", key: "ai_model", kind: "text", advanced: true },
      { section: "plonkit", key: "ai_batch", kind: "int", min: 5, max: 50, advanced: true },
      { section: "plonkit", key: "ai_pause_s", kind: "float", min: 0, max: 60, advanced: true },
      { section: "plonkit", key: "keywords", kind: "categoryList", advanced: true },
    ],
  },
  {
    id: "map",
    fileSections: ["map","plonk"],
    fields: [
      { section: "map", key: "enabled", kind: "bool" },
      { section: "plonk", key: "enabled", kind: "bool" },
      { section: "map", key: "max_zoom", kind: "int", min: 2, max: 19, needs: ["map", "enabled"] },
      { section: "plonk", key: "steps", kind: "int", min: 10, max: 250, advanced: true },
      { section: "plonk", key: "points", kind: "int", min: 64, max: 2048, advanced: true },
      { section: "plonk", key: "zone_share", kind: "float", min: 0.25, max: 1, step: 0.05, advanced: true },
      { section: "plonk", key: "zone_link_km", kind: "float", min: 20, max: 1000, advanced: true },
      { section: "plonk", key: "zone_min_part", kind: "float", min: 0.01, max: 0.5, step: 0.01, advanced: true },
      { section: "map", key: "attribution", kind: "text", advanced: true },
      { section: "map", key: "tile_filter", kind: "text", advanced: true },
      { section: "map", key: "close_zoom", kind: "int", min: 2, max: 19, needs: ["map", "enabled"] },
      { section: "map", key: "tile_filter_close", kind: "text", advanced: true },
    ],
  },
  {
    id: "capture",
    fileSections: ["capture"],
    fields: [
      { section: "capture", key: "notify", kind: "bool" },
      { section: "capture", key: "sound", kind: "bool", needs: ["capture", "notify"] },
      { section: "capture", key: "save_to_disk", kind: "bool" },
      { section: "capture", key: "keep_last", kind: "int", min: 0, needs: ["capture", "save_to_disk"] },
      { section: "capture", key: "source", kind: "select", options: ["window","monitor","both"], advanced: true },
      { section: "capture", key: "crop", kind: "rect", advanced: true },
      { section: "capture", key: "masks", kind: "rects", advanced: true },
    ],
  },
  {
    id: "marks",
    fileSections: ["rules"],
    fields: [
      { section: "marks", key: "enabled", kind: "bool" },
      { section: "marks", key: "max_marks", kind: "int", min: 1, max: 20, needs: ["marks", "enabled"] },
      { section: "marks", key: "upscale_to_px", kind: "int", min: 64, max: 2048, needs: ["marks", "enabled"] },
      { section: "marks", key: "max_upscale", kind: "float", min: 1, max: 8, step: 0.5, needs: ["marks", "enabled"] },
      { section: "rules", key: "scripts", kind: "bool" },
      { section: "rules", key: "letters", kind: "bool" },
      { section: "rules", key: "places", kind: "bool" },
      { section: "rules", key: "detail", kind: "bool", needs: ["rules", "places"] },
      { section: "rules", key: "place_max_spread_km", kind: "float", min: 50, max: 3000, advanced: true, needs: ["rules", "places"] },
      { section: "rules", key: "prior_min", kind: "float", min: 0, max: 1, step: 0.05, advanced: true, needs: ["rules", "places"] },
      { section: "rules", key: "place_min_len", kind: "int", min: 3, max: 20, advanced: true, needs: ["rules", "places"] },
      { section: "marks", key: "parallel", kind: "int", min: 1, max: 8, advanced: true },
      { section: "marks", key: "model", kind: "text", advanced: true },
      { section: "marks", key: "max_tokens", kind: "int", min: 50, max: 4000, advanced: true },
      { section: "marks", key: "prompt", kind: "textarea", advanced: true },
    ],
  },
  {
    id: "locks",
    fileSections: [],
    fields: [
      { section: "locks", key: "enabled", kind: "bool" },
      { section: "locks", key: "auto_country", kind: "bool", needs: ["locks", "enabled"] },
      { section: "locks", key: "auto_region", kind: "bool", needs: ["locks", "enabled"] },
      { section: "locks", key: "propose_city", kind: "bool", needs: ["locks", "enabled"] },
      { section: "locks", key: "region_radius_km", kind: "float", min: 1, max: 100, advanced: true, needs: ["locks", "auto_region"] },
      { section: "locks", key: "region_places_km", kind: "float", min: 5, max: 300, advanced: true, needs: ["locks", "auto_region"] },
    ],
  },
  {
    id: "dataset",
    fileSections: ["dataset"],
    fields: [
      { section: "dataset", key: "enabled", kind: "bool" },
      { section: "dataset", key: "ask_guessed", kind: "bool", needs: ["dataset", "enabled"] },
      { section: "dataset", key: "max_confusions", kind: "int", min: 0, max: 10, needs: ["dataset", "ask_guessed"] },
    ],
  },
];

/** Storage: sizes, limit of the caches that grow, "Empty" buttons (StoragePanel). */
GROUPS.push(
  {
    id: "storage",
    fileSections: [],
    fields: [
      { section: "storage", key: "max_cache_mb", kind: "int", min: 50, max: 100000 },
    ],
  },
  {
    id: "engine",
    fileSections: ["server"],
    fields: [
      { section: "debug", key: "enabled", kind: "bool" },
    ],
  },
);

