// One-line summaries of the coach sections: readable even when the section is collapsed.
import type { Analysis } from "./engine";
import { i18n, isEmptyValue, pct, quote, t, tn } from "./i18n";
import { certainProof, circled, clearLeader, contenders, countryName, flag, num, proofOf, tipsByCountry, viable } from "./engine";

const analysing = () => t("sum.analysing");

export function answer(a: Analysis): string {
  const proof = proofOf(a);
  if (proof) {
    const where = `${flag(proof.country)} ${countryName(proof.country)}${proof.region ? ` · ${proof.region}` : ""}`;
    return `${where} · ${t(proof.confirmed ? "sum.certain" : proof.source === "marks" ? "sum.very_likely" : "sum.to_confirm")}`;
  }
  if (!a.scores?.length) return analysing();
  const leader = clearLeader(a);
  if (leader) return `${flag(leader.code)} ${countryName(leader.code)} ${pct(leader.probability)}`;
  return t("sum.hesitation", { flags: contenders(a).map((s) => flag(s.code)).join(" ") });
}

export function capture(a: Analysis): string {
  const time = `${new Date(a.at).toLocaleTimeString(i18n.lang)} · ${a.captureMs} ms`;
  return a.guessedCrop ? `${time} · ${t("sum.crop_guessed")}` : time;
}

export function countries(a: Analysis): string {
  const scores = a.scores ?? [];
  const certain = certainProof(a);
  if (certain) {
    const ruledOut = scores.filter((s) => s.code !== certain.country).length;
    return `${flag(certain.country)} ${t("sum.certain")}${ruledOut ? ` · ${tn("sum.ruled_out", ruledOut)}` : ""}`;
  }
  const proof = proofOf(a);
  if (proof?.source === "marks") return `${flag(proof.country)} ${t("sum.very_likely")} · ${t("sum.your_marks")}`;
  if (proof) return `${flag(proof.country)} ${t(proof.certainty === "strong" ? "sum.very_likely" : "sum.likely")} · ${t("sum.read_by_ai")}`;
  return viable(a).slice(0, 3).map((s) => `${flag(s.code)} ${pct(s.probability)}`).join(" · ") || analysing();
}

export function metas(a: Analysis): string {
  if (!a.lookfor) return analysing();
  return a.lookfor.map((lf) => lf.label).join(" · ") || t("sum.no_meta");
}

export function tips(a: Analysis): string {
  const groups = tipsByCountry(a);
  const count = groups.reduce((n, g) => n + g.tips.length, 0);
  const base = groups.length === 1 ? t("sum.tips_for", { n: count, country: countryName(groups[0].code) })
    : tn("sum.tips_countries", count, { countries: groups.length });
  return a.translation === "pending" ? `${base} · ${t("sum.translating")}` : base;
}

export function vision(a: Analysis): string {
  const v = a.vision;
  if (v.status === "off") return t("sum.off");
  if (v.status === "pending") return t("sum.vision_pending");
  if (v.status === "error") return t("sum.unavailable");
  const text = v.fiche.signs_and_text;
  const hasText = typeof text === "string" ? !isEmptyValue(text) : Array.isArray(text) && text.length > 0;
  return `${t(hasText ? "sum.text_read" : "sum.no_text")} · ${num(v.seconds)} s`;
}

export function round(a: Analysis): string {
  return a.labelled ? `${flag(a.labelled.country)} ${t("sum.saved")}` : t("sum.where_was_it");
}

/** Marks: the text read on each, by its number ("① “Repkény utca” · ② unreadable"). */
export function marks(a: Analysis): string {
  return a.marks
    .map((m) => {
      const read = m.text.join(" ");
      const what = m.status === "pending" ? t("sum.reading") : m.status === "error" ? t("sum.failed")
        : read ? quote(read.length > 36 ? `${read.slice(0, 35)}…` : read) : t(m.unreadable ? "sum.unreadable" : "sum.no_text");
      return `${circled(m.n)} ${what}`;
    })
    .join(" · ");
}
