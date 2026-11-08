// One-line summaries of the coach sections: readable even when the section is collapsed.
import type { Analysis } from "./engine";
import { certainProof, circled, clearLeader, contenders, countryName, flag, fr, proofOf, tipsByCountry, viable } from "./engine";

const pct = (p: number) => `${Math.round(p * 100)} %`;
const EMPTY = /^(non visible|aucun|indéterminé)?\.?$/i;
const analysing = "analyse en cours…";

export function answer(a: Analysis): string {
  const proof = proofOf(a);
  if (proof) {
    const where = `${flag(proof.country)} ${countryName(proof.country)}${proof.region ? ` · ${proof.region}` : ""}`;
    return proof.confirmed ? `${where} · certain` : proof.source === "marks" ? `${where} · très probable` : `${where} · à confirmer`;
  }
  if (!a.scores?.length) return analysing;
  const leader = clearLeader(a);
  if (leader) return `${flag(leader.code)} ${countryName(leader.code)} ${pct(leader.probability)}`;
  return `hésitation · ${contenders(a).map((s) => flag(s.code)).join(" ")}`;
}

export function capture(a: Analysis): string {
  return `${new Date(a.at).toLocaleTimeString("fr-FR")} · ${a.captureMs} ms`;
}

export function countries(a: Analysis): string {
  const scores = a.scores ?? [];
  const certain = certainProof(a);
  if (certain) {
    const ruledOut = scores.filter((s) => s.code !== certain.country).length;
    return `${flag(certain.country)} certain${ruledOut ? ` · ${ruledOut} écartés` : ""}`;
  }
  const proof = proofOf(a);
  if (proof?.source === "marks") return `${flag(proof.country)} très probable · tes marques`;
  if (proof) return `${flag(proof.country)} ${proof.certainty === "forte" ? "très probable" : "probable"} · lu par l'IA`;
  return viable(a).slice(0, 3).map((s) => `${flag(s.code)} ${pct(s.probability)}`).join(" · ") || analysing;
}

export function metas(a: Analysis): string {
  if (!a.lookfor) return analysing;
  return a.lookfor.map((lf) => lf.label).join(" · ") || "aucune meta";
}

export function tips(a: Analysis): string {
  const groups = tipsByCountry(a);
  const count = groups.reduce((n, g) => n + g.tips.length, 0);
  const base = groups.length === 1 ? `${count} pour ${countryName(groups[0].code)}` : `${count} astuces · ${groups.length} pays`;
  return a.translation === "pending" ? `${base} · traduction…` : base;
}

export function vision(a: Analysis): string {
  const v = a.vision;
  if (v.status === "off") return "désactivé";
  if (v.status === "pending") return "analyse approfondie en cours…";
  if (v.status === "error") return "indisponible";
  const text = v.fiche.panneaux_et_texte;
  const hasText = typeof text === "string" ? !EMPTY.test(text.trim()) : Array.isArray(text) && text.length > 0;
  return `${hasText ? "texte lu · " : "pas de texte · "}${fr(v.seconds)} s`;
}

export function round(a: Analysis): string {
  return a.labelled ? `${flag(a.labelled.country)} enregistré` : "c'était où ?";
}

/** Marks: the text read on each, by its number ("① « Repkény utca » · ② illisible"). */
export function marks(a: Analysis): string {
  return a.marks
    .map((m) => {
      const read = m.text.join(" ");
      const what = m.status === "pending" ? "lecture…" : m.status === "error" ? "échec"
        : read ? `« ${read.length > 36 ? `${read.slice(0, 35)}…` : read} »` : m.unreadable ? "illisible" : "pas de texte";
      return `${circled(m.n)} ${what}`;
    })
    .join(" · ");
}
