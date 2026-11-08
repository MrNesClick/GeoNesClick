"""Local ranking by country with StreetCLIP (level 1, instant)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from .config import StreetClipConfig


@dataclass
class CountryScore:
    name: str
    code: str
    probability: float


class StreetClip:
    def __init__(self, cfg: StreetClipConfig) -> None:
        self.cfg = cfg
        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if cfg.device == "auto" else cfg.device
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        # Pinned version, weights in safetensors only (2026-11-07): the repository's main version only has
        # pytorch_model.bin (pickle, which can run code); the library downloaded it THEN went to fetch
        # the converted safetensors: 3.2 GB instead of 1.7 GB.
        self.model = CLIPModel.from_pretrained(cfg.model, revision=cfg.revision, use_safetensors=True,
                                               torch_dtype=dtype).to(self.device).eval()
        self.processor = CLIPProcessor.from_pretrained(cfg.model, revision=cfg.revision)  # offline if cached
        self.set_labels(cfg)

    def set_labels(self, cfg: StreetClipConfig) -> None:
        """Candidate countries and prompt: text vectors recomputed (also on the fly, from the Settings)."""
        names = list(cfg.countries)
        with torch.inference_mode():
            text_in = self.processor(
                text=[cfg.prompt.format(n) for n in names], return_tensors="pt", padding=True
            ).to(self.device)
            emb = self.model.get_text_features(**text_in).pooler_output  # Transformers 5: output object
        self.cfg, self.names, self.text_emb = cfg, names, emb / emb.norm(dim=-1, keepdim=True)

    def predict(self, img: Image.Image) -> tuple[list[CountryScore], float]:
        scores, ms, _, _ = self.analyse(img)
        return scores, ms

    def analyse(self, img: Image.Image) -> tuple[list[CountryScore], float, np.ndarray, torch.Tensor]:
        """Top countries, duration (ms), normalised image vector (Plonk It tips) and [CLS] token (PLONK).

        A single ViT pass: get_image_features() amounts to projecting the vision_model's pooler_output,
        and PLONK reads the [CLS] token of last_hidden_state from this same pass (measured: cosine 0.99998 between
        our fp16 and the fp32 of its training, spikes/plonk_bench.py).
        """
        t0 = time.perf_counter()
        with torch.inference_mode():
            img_in = self.processor(images=img, return_tensors="pt").to(self.device, self.model.dtype)
            vis = self.model.vision_model(pixel_values=img_in["pixel_values"])
            emb = self.model.visual_projection(vis.pooler_output)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            probs = (self.model.logit_scale.exp() * emb @ self.text_emb.T).softmax(dim=-1)[0].float()
            cls = vis.last_hidden_state[:, 0]
        top = probs.topk(min(self.cfg.top_k, len(self.names)))
        scores = [
            CountryScore(self.names[i], self.cfg.countries[self.names[i]], round(p, 4))
            for p, i in zip(top.values.tolist(), top.indices.tolist(), strict=True)
        ]
        return scores, (time.perf_counter() - t0) * 1000, emb[0].float().cpu().numpy(), cls

    def encode_texts(self, texts: list[str], batch: int = 64) -> np.ndarray:
        """Normalised vectors of texts (truncated to CLIP's 77 tokens), in batches."""
        out = []
        with torch.inference_mode():
            for i in range(0, len(texts), batch):
                inp = self.processor(text=texts[i:i + batch], return_tensors="pt", padding=True,
                                     truncation=True, max_length=77).to(self.device)
                emb = self.model.get_text_features(**inp).pooler_output.float()
                out.append(torch.nn.functional.normalize(emb, dim=-1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 0), dtype=np.float32)
