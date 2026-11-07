"""Classement local par pays avec StreetCLIP (niveau 1, instantané)."""

from __future__ import annotations

import time
from dataclasses import dataclass

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
        self.model = CLIPModel.from_pretrained(cfg.model, torch_dtype=dtype).to(self.device).eval()
        self.processor = CLIPProcessor.from_pretrained(cfg.model)  # hors ligne si en cache (__main__)
        self.names = list(cfg.countries)
        with torch.inference_mode():
            text_in = self.processor(
                text=[cfg.prompt.format(n) for n in self.names], return_tensors="pt", padding=True
            ).to(self.device)
            emb = self.model.get_text_features(**text_in).pooler_output  # Transformers 5 : objet de sortie
            self.text_emb = emb / emb.norm(dim=-1, keepdim=True)

    def predict(self, img: Image.Image) -> tuple[list[CountryScore], float]:
        t0 = time.perf_counter()
        with torch.inference_mode():
            img_in = self.processor(images=img, return_tensors="pt").to(self.device, self.model.dtype)
            emb = self.model.get_image_features(**img_in).pooler_output
            emb = emb / emb.norm(dim=-1, keepdim=True)
            probs = (self.model.logit_scale.exp() * emb @ self.text_emb.T).softmax(dim=-1)[0].float()
        top = probs.topk(min(self.cfg.top_k, len(self.names)))
        scores = [
            CountryScore(self.names[i], self.cfg.countries[self.names[i]], round(p, 4))
            for p, i in zip(top.values.tolist(), top.indices.tolist(), strict=True)
        ]
        return scores, (time.perf_counter() - t0) * 1000
