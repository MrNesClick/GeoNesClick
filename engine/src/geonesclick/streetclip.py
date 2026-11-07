"""Classement local par pays avec StreetCLIP (niveau 1, instantané)."""

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
        # Version figée, poids en safetensors seulement (2026-11-07) : la version principale du dépôt n'a que
        # pytorch_model.bin (pickle, qui peut exécuter du code) ; la bibliothèque le téléchargeait PUIS allait chercher
        # le safetensors de la conversion : 3,2 Go au lieu de 1,7 Go.
        self.model = CLIPModel.from_pretrained(cfg.model, revision=cfg.revision, use_safetensors=True,
                                               torch_dtype=dtype).to(self.device).eval()
        self.processor = CLIPProcessor.from_pretrained(cfg.model, revision=cfg.revision)  # hors ligne si en cache
        self.set_labels(cfg)

    def set_labels(self, cfg: StreetClipConfig) -> None:
        """Pays candidats et prompt : vecteurs texte recalculés (aussi à chaud, depuis les Réglages)."""
        names = list(cfg.countries)
        with torch.inference_mode():
            text_in = self.processor(
                text=[cfg.prompt.format(n) for n in names], return_tensors="pt", padding=True
            ).to(self.device)
            emb = self.model.get_text_features(**text_in).pooler_output  # Transformers 5 : objet de sortie
        self.cfg, self.names, self.text_emb = cfg, names, emb / emb.norm(dim=-1, keepdim=True)

    def predict(self, img: Image.Image) -> tuple[list[CountryScore], float]:
        scores, ms, _, _ = self.analyse(img)
        return scores, ms

    def analyse(self, img: Image.Image) -> tuple[list[CountryScore], float, np.ndarray, torch.Tensor]:
        """Top des pays, durée (ms), vecteur normalisé de l'image (astuces Plonk It) et jeton [CLS] (PLONK).

        Une seule passe du ViT : get_image_features() revient à projeter le pooler_output du vision_model,
        et PLONK lit le jeton [CLS] de last_hidden_state de cette même passe (mesuré : cosinus 0,99998 entre
        notre fp16 et le fp32 de son entraînement, spikes/plonk_bench.py).
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
        """Vecteurs normalisés de textes (tronqués aux 77 jetons de CLIP), par lots."""
        out = []
        with torch.inference_mode():
            for i in range(0, len(texts), batch):
                inp = self.processor(text=texts[i:i + batch], return_tensors="pt", padding=True,
                                     truncation=True, max_length=77).to(self.device)
                emb = self.model.get_text_features(**inp).pooler_output.float()
                out.append(torch.nn.functional.normalize(emb, dim=-1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 0), dtype=np.float32)
