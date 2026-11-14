<script lang="ts">
// What an update brings: the CHANGELOG sections since the installed version (setup.rs, whats_new), in the UI's
// language: CHANGELOG.<lang>.md when the bundle has it, CHANGELOG.md (English) otherwise.
// The Markdown is read line by line into headings, items and paragraphs, shown as text (never as HTML).
import { i18n } from "../i18n";

export interface Release { version: string; text: string }
/** The releases by language ("en", "fr"…), as setup.rs sends them. */
export type WhatsNewByLang = Record<string, Release[]>;
/** The releases in the UI's language, English otherwise; a list saved before the languages (0.5.0) is English. */
export function inLanguage(byLang: WhatsNewByLang | Release[] | undefined): Release[] {
  if (Array.isArray(byLang)) return byLang;
  return byLang?.[i18n.lang] ?? byLang?.en ?? [];
}
</script>

<script setup lang="ts">
import { computed } from "vue";
import { t, type Key } from "../i18n";

const props = defineProps<{ releases: WhatsNewByLang | Release[] }>();

type Block = { kind: "heading" | "item" | "text"; text: string };

/** Links keep their words, code its letters: "[CHANGELOG](https://…)" → "CHANGELOG", "`crop`" → "crop". */
/** Keep a Changelog's English headings in the UI's language (CHANGELOG.<lang>.md already writes them in its own). */
const HEADINGS: Record<string, Key> = {
  Added: "whats_new.added", Changed: "whats_new.changed", Deprecated: "whats_new.deprecated", Removed: "whats_new.removed",
  Fixed: "whats_new.fixed", Security: "whats_new.security", Migration: "whats_new.migration",
};
const heading = (s: string) => (s in HEADINGS ? t(HEADINGS[s]) : s);
const plain = (s: string) => s.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/`([^`]*)`/g, "$1").replace(/\*\*([^*]+)\*\*/g, "$1");

function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("#")) out.push({ kind: "heading", text: heading(plain(line.replace(/^#+\s*/, ""))) });
    else if (line.startsWith("- ")) out.push({ kind: "item", text: plain(line.slice(2)) });
    else if (out.length && out[out.length - 1].kind !== "heading") out[out.length - 1].text += ` ${plain(line)}`;
    else out.push({ kind: "text", text: plain(line) });
  }
  return out;
}

const shown = computed(() => inLanguage(props.releases).map((r) => ({ version: r.version, blocks: blocks(r.text) })));
</script>

<template>
  <div class="space-y-3">
    <section v-for="r in shown" :key="r.version">
      <h2 class="font-bold text-papier">{{ t("setup.whats_new", { version: r.version }) }}</h2>
      <template v-for="(b, i) in r.blocks" :key="i">
        <h3 v-if="b.kind === 'heading'" class="mt-2 text-[0.95rem] font-bold text-courbe">{{ b.text }}</h3>
        <p v-else :class="b.kind === 'item' ? 'mt-1 pl-4 -indent-3' : 'mt-1'" class="text-[0.95rem] text-papier">{{ b.kind === "item" ? "• " : "" }}{{ b.text }}</p>
      </template>
    </section>
  </div>
</template>
