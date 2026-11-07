"""Banc d'essai : comment chercher dans les astuces Plonk It collectées ?

Compare, sur les mêmes données locales (python -m geonesclick.plonkit collect) :
  dict      dictionnaire en mémoire (référence)
  fts5      SQLite FTS5, classement BM25 (inclus dans Python)
  tantivy   Tantivy (moteur façon Lucene, en Rust), avec tolérance aux fautes de frappe
  e5        recherche sémantique : intfloat/multilingual-e5-small (local, multilingue)
  clip      StreetCLIP : la capture comparée directement aux textes des astuces (sans niveau 2)

Mesures : construction de l'index, taille, latence (recherche par pays, par mots, avec fautes), et justesse
sur le jeu de test étiqueté : la fiche du niveau 2 (FR, et une variante EN) sert de requête, et on regarde à
quel rang chaque approche place le bon pays (parmi tous, et parmi le top 5 de StreetCLIP).

Lancer : uv run --with tantivy==0.26.2 python spikes/search_bench.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sqlite3
import statistics
import sys
import time
import tomllib
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import tantivy  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from transformers import AutoModel, AutoTokenizer  # noqa: E402

from geonesclick.config import load_config  # noqa: E402
from geonesclick.plonkit import load_tips  # noqa: E402
from geonesclick.streetclip import StreetClip  # noqa: E402
from geonesclick.vision import VisionClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get("BENCH_DIR", "/tmp/ggc-search-bench"))
FICHE_FIELDS = [
    "sens_circulation", "preuve_circulation", "marquage_routier", "poteaux", "bornes_et_glissieres",
    "panneaux_et_texte", "plaques_immatriculation", "architecture", "vegetation_et_sol", "relief",
    "camera_et_voiture_google", "autres_indices",
]
EMPTY = re.compile(r"^(non visible|aucun|indéterminé|not visible|none|unknown|n/a)?\.?$", re.I)
E5 = "intfloat/multilingual-e5-small"
KEYWORDS = ["bollard", "yellow center line", "concrete pole holes", "cyrillic", "snow poles", "guardrail"]
TYPOS = ["bolard", "guardrial", "cyrilic", "bolards"]


def clean(md: str) -> str:
    return re.sub(r"[*_`#>\[\]]|\(https?://[^)]*\)", " ", md).strip()


def timeit(fn, repeat=200) -> float:
    """Latence médiane en microsecondes."""
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1e6)
    return statistics.median(samples)


def observations(fiche: dict) -> list[str]:
    out = []
    for key in FICHE_FIELDS:
        v = fiche.get(key)
        v = " ; ".join(map(str, v)) if isinstance(v, list) else str(v or "")
        if v.strip() and not EMPTY.match(v.strip()):
            out.append(v.strip())
    return out


# --- moteurs ---------------------------------------------------------------------------------------
class Fts5:
    def __init__(self, tips, path: Path):
        path.unlink(missing_ok=True)
        self.con = sqlite3.connect(path)
        self.con.executescript("""
            CREATE TABLE tip(id INTEGER PRIMARY KEY, country TEXT NOT NULL, text TEXT NOT NULL);
            CREATE INDEX tip_country ON tip(country);
            CREATE VIRTUAL TABLE tip_fts USING fts5(text, content='tip', content_rowid='id',
                tokenize='porter unicode61 remove_diacritics 2');
        """)
        self.con.executemany("INSERT INTO tip VALUES (?, ?, ?)", [(i, t.country, clean(t.text)) for i, t in enumerate(tips)])
        self.con.execute("INSERT INTO tip_fts(tip_fts) VALUES ('rebuild')")
        self.con.commit()
        self.size = path.stat().st_size

    def by_country(self, codes):
        q = f"SELECT id FROM tip WHERE country IN ({','.join('?' * len(codes))})"
        return [r[0] for r in self.con.execute(q, codes)]

    def search(self, text, k=50):
        words = re.findall(r"\w{3,}", text.lower())
        if not words:
            return []
        match = " OR ".join(f'"{w}"' for w in words)  # chaque mot entre guillemets : pas d'injection de syntaxe
        rows = self.con.execute(
            "SELECT rowid, -bm25(tip_fts) FROM tip_fts WHERE tip_fts MATCH ? ORDER BY bm25(tip_fts) LIMIT ?", (match, k)
        )
        return list(rows)


class Tantivy:
    def __init__(self, tips, path: Path):
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True)
        sb = tantivy.SchemaBuilder()
        sb.add_text_field("text", stored=False, tokenizer_name="en_stem")
        sb.add_text_field("country", stored=False, tokenizer_name="raw")
        sb.add_unsigned_field("doc", stored=True, indexed=False)
        self.index = tantivy.Index(sb.build(), path=str(path))
        w = self.index.writer()
        for i, t in enumerate(tips):
            w.add_document(tantivy.Document(text=clean(t.text), country=t.country, doc=i))
        w.commit()
        w.wait_merging_threads()
        self.index.reload()
        self.searcher = self.index.searcher()
        self.size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

    def _run(self, query, k):
        res = self.searcher.search(query, k)
        return [(self.searcher.doc(addr)["doc"][0], score) for score, addr in res.hits]

    def by_country(self, codes):
        q = self.index.parse_query(" OR ".join(f"country:{c}" for c in codes))
        return [d for d, _ in self._run(q, 10_000)]

    def search(self, text, k=50, fuzzy=False):
        words = re.findall(r"\w{3,}", text.lower())
        if not words:
            return []
        fuzzy_fields = {"text": (False, 1, True)} if fuzzy else {}
        q = self.index.parse_query(" ".join(words), ["text"], fuzzy_fields=fuzzy_fields)
        return self._run(q, k)


class E5Search:
    def __init__(self, tips, device):
        self.device = device
        self.tok = AutoTokenizer.from_pretrained(E5)
        dtype = torch.float16 if device == "cuda" else torch.float32
        self.model = AutoModel.from_pretrained(E5, torch_dtype=dtype).to(device).eval()
        t0 = time.perf_counter()
        self.emb = torch.cat([self._encode([f"passage: {clean(t.text)}" for t in tips[i:i + 64]])
                              for i in range(0, len(tips), 64)])
        self.build_s = time.perf_counter() - t0
        self.size = self.emb.numel() * 4  # stocké en float32

    @torch.inference_mode()
    def _encode(self, texts):
        batch = self.tok(texts, padding=True, truncation=True, max_length=512, return_tensors="pt").to(self.device)
        out = self.model(**batch).last_hidden_state
        mask = batch["attention_mask"].unsqueeze(-1).to(out.dtype)
        emb = (out * mask).sum(1) / mask.sum(1)
        return torch.nn.functional.normalize(emb.float(), dim=-1)

    def search(self, text, k=50):
        sims = (self.emb @ self._encode([f"query: {text}"])[0])
        top = sims.topk(min(k, len(sims)))
        return list(zip(top.indices.tolist(), top.values.tolist(), strict=True))


class ClipTips:
    """La capture comparée directement aux astuces (texte tronqué à 77 jetons par CLIP)."""

    def __init__(self, tips, clip: StreetClip):
        self.clip = clip
        t0 = time.perf_counter()
        chunks = []
        with torch.inference_mode():
            for i in range(0, len(tips), 64):
                inp = clip.processor(text=[clean(t.text) for t in tips[i:i + 64]], return_tensors="pt",
                                     padding=True, truncation=True, max_length=77).to(clip.device)
                e = clip.model.get_text_features(**inp).pooler_output
                chunks.append(torch.nn.functional.normalize(e.float(), dim=-1))
        self.emb = torch.cat(chunks)
        self.build_s = time.perf_counter() - t0

    def search_image(self, img, k=50):
        with torch.inference_mode():
            inp = self.clip.processor(images=img, return_tensors="pt").to(self.clip.device, self.clip.model.dtype)
            e = torch.nn.functional.normalize(self.clip.model.get_image_features(**inp).pooler_output.float(), dim=-1)
        sims = self.emb @ e[0]
        top = sims.topk(min(k, len(sims)))
        return list(zip(top.indices.tolist(), top.values.tolist(), strict=True))


# --- justesse -------------------------------------------------------------------------------------
def country_ranking(tips, per_observation_hits) -> list[str]:
    """Pour chaque observation, le meilleur score de chaque pays (normalisé à 1) ; somme sur les observations."""
    total = defaultdict(float)
    for hits in per_observation_hits:
        best = {}
        for doc, score in hits:
            c = tips[doc].country
            best[c] = max(best.get(c, 0.0), score)
        if best:
            top = max(best.values()) or 1.0
            for c, s in best.items():
                total[c] += s / top
    return sorted(total, key=total.get, reverse=True)


def rank_of(country, ranking, pool=None):
    ranking = [c for c in ranking if pool is None or c in pool]
    return ranking.index(country) + 1 if country in ranking else None


async def fiches_for(labels, cfg) -> dict:
    cache = WORK / "fiches.json"
    cached = json.loads(cache.read_text()) if cache.exists() else {}
    fr_client = VisionClient(cfg.vision)
    en_cfg = cfg.vision.model_copy(update={"prompt": cfg.vision.prompt + (
        "\n\nIMPORTANT : rédige toutes les valeurs du JSON en anglais ; les clés restent identiques.")})
    en_client = VisionClient(en_cfg)
    for lb in labels:
        for lang, client in (("fr", fr_client), ("en", en_client)):
            key = f"{lb['file']}|{lang}"
            if key in cached:
                continue
            img = Image.open(ROOT / "dataset" / "images" / lb["file"]).convert("RGB")
            print(f"  fiche {lang} pour {lb['country']}…", flush=True)
            fiche, _ = await client.describe(img)
            cached[key] = fiche
            cache.write_text(json.dumps(cached, ensure_ascii=False, indent=1))
    return cached


def fusion(labels, tips, clip, cliptips, top_n=3):
    """StreetCLIP (pays) × image → astuces (moyenne des 3 meilleures astuces du pays), sans paramètre à régler :
    chaque score devient une probabilité avec la température de CLIP, puis on multiplie."""
    codes = [clip.cfg.countries[n] for n in clip.names]
    of_country = defaultdict(list)
    for i, t in enumerate(tips):
        of_country[t.country].append(i)
    scale = clip.model.logit_scale.exp().float().item()
    rows = []
    for lb in labels:
        img = Image.open(ROOT / "dataset" / "images" / lb["file"]).convert("RGB")
        with torch.inference_mode():
            inp = clip.processor(images=img, return_tensors="pt").to(clip.device, clip.model.dtype)
            e = torch.nn.functional.normalize(clip.model.get_image_features(**inp).pooler_output.float(), dim=-1)[0]
        p_country = (scale * (clip.text_emb.float() @ e)).softmax(-1)
        sims = cliptips.emb @ e
        tip_score = torch.tensor([
            sims[of_country[c]].topk(min(top_n, len(of_country[c]))).values.mean().item() if of_country[c] else -1.0
            for c in codes
        ], device=e.device)
        p_tips = (scale * tip_score).softmax(-1)
        p_fused = (p_country.log() + p_tips.log()).softmax(-1)

        def rank(p):
            order = [codes[i] for i in p.argsort(descending=True).tolist()]
            return order.index(lb["country"]) + 1

        best = sims[of_country[lb["country"]]].topk(3)
        rows.append({
            "country": lb["country"], "streetclip": rank(p_country), "tips": rank(p_tips), "fusion": rank(p_fused),
            "p_true_streetclip": round(p_country[codes.index(lb["country"])].item(), 3),
            "p_true_fusion": round(p_fused[codes.index(lb["country"])].item(), 3),
            "best_tips": [tips[of_country[lb["country"]][i]].section for i in best.indices.tolist()],
        })
    return rows


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    ours = set(cfg.streetclip.countries.values())
    tips = [t for t in load_tips() if t.country in ours and t.text]
    if not tips:
        sys.exit("aucune astuce : lance d'abord python -m geonesclick.plonkit collect")
    chars = sum(len(t.text) for t in tips)
    print(f"Corpus : {len(tips)} astuces, {len({t.country for t in tips})} pays, {chars / 1e6:.1f} Mo de texte\n")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    report: dict = {"corpus": {"tips": len(tips), "countries": len({t.country for t in tips}), "chars": chars}}

    # Construction
    t0 = time.perf_counter()
    by_country = defaultdict(list)
    for i, t in enumerate(tips):
        by_country[t.country].append(i)
    dict_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    fts = Fts5(tips, WORK / "tips.sqlite")
    fts_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    tan = Tantivy(tips, WORK / "tantivy")
    tan_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    e5 = E5Search(tips, device)
    e5_load_s = time.perf_counter() - t0 - e5.build_s
    clip = StreetClip(cfg.streetclip)
    cliptips = ClipTips(tips, clip)
    report["build"] = {
        "dict": {"s": dict_s, "bytes": None},
        "fts5": {"s": fts_s, "bytes": fts.size},
        "tantivy": {"s": tan_s, "bytes": tan.size},
        "e5": {"s": e5.build_s, "load_s": e5_load_s, "bytes": e5.size, "device": device},
        "clip": {"s": cliptips.build_s, "bytes": cliptips.emb.numel() * 4},
    }

    # Latences
    five = ["NO", "SE", "FI", "EE", "LV"]
    assert sorted(fts.by_country(five)) == sorted(i for c in five for i in by_country[c])
    assert sorted(tan.by_country(five)) == sorted(i for c in five for i in by_country[c])
    lat = {
        "by_country": {
            "dict": timeit(lambda: [i for c in five for i in by_country[c]]),
            "fts5": timeit(lambda: fts.by_country(five)),
            "tantivy": timeit(lambda: tan.by_country(five)),
        },
        "keywords": {
            "fts5": statistics.median(timeit(lambda q=q: fts.search(q), 50) for q in KEYWORDS),
            "tantivy": statistics.median(timeit(lambda q=q: tan.search(q), 50) for q in KEYWORDS),
            "tantivy_fuzzy": statistics.median(timeit(lambda q=q: tan.search(q, fuzzy=True), 50) for q in KEYWORDS),
            "e5": statistics.median(timeit(lambda q=q: e5.search(q), 20) for q in KEYWORDS),
        },
    }
    img0 = Image.open(next((ROOT / "dataset" / "images").glob("*.png"))).convert("RGB")
    lat["image"] = {"clip": timeit(lambda: cliptips.search_image(img0), 10)}
    report["latency_us"] = lat
    report["typos"] = {q: {"fts5": len(fts.search(q)), "tantivy": len(tan.search(q)),
                           "tantivy_fuzzy": len(tan.search(q, fuzzy=True))} for q in TYPOS}
    report["keywords_hits"] = {q: {"fts5": len(fts.search(q)), "tantivy": len(tan.search(q))} for q in KEYWORDS}

    # Justesse sur le jeu de test
    labels = tomllib.loads((ROOT / "dataset" / "labels.toml").read_text())["capture"]
    fiches = asyncio.run(fiches_for(labels, cfg))
    rows = []
    for lb in labels:
        img = Image.open(ROOT / "dataset" / "images" / lb["file"]).convert("RGB")
        clip_top = [s.code for s in clip.predict(img)[0]][:5]
        row = {"country": lb["country"], "streetclip_rank_top5": rank_of(lb["country"], clip_top)}
        for lang in ("fr", "en"):
            obs = observations(fiches[f"{lb['file']}|{lang}"])
            row[f"n_obs_{lang}"] = len(obs)
            for name, fn in (("fts5", fts.search), ("tantivy", lambda q: tan.search(q, fuzzy=True)), ("e5", e5.search)):
                ranking = country_ranking(tips, [fn(o) for o in obs])
                row[f"{name}_{lang}"] = rank_of(lb["country"], ranking)
                row[f"{name}_{lang}_top5"] = rank_of(lb["country"], ranking, set(clip_top))
        ranking = country_ranking(tips, [cliptips.search_image(img)])
        row["clip_img"] = rank_of(lb["country"], ranking)
        row["clip_img_top5"] = rank_of(lb["country"], ranking, set(clip_top))
        rows.append(row)
    report["accuracy"] = rows
    report["fusion"] = fusion(labels, tips, clip, cliptips)
    (WORK / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
