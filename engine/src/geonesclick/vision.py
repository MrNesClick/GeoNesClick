"""Fiche d'indices par un modèle de vision distant (niveau 2, asynchrone)."""

from __future__ import annotations

import base64
import io
import json
import time
from typing import Any

from openai import AsyncOpenAI
from PIL import Image

from .config import VisionConfig, read_secret


class VisionError(RuntimeError):
    pass


class VisionClient:
    def __init__(self, cfg: VisionConfig) -> None:
        self.cfg = cfg
        key = read_secret(cfg.api_key_env)
        self.client = (
            AsyncOpenAI(base_url=cfg.base_url, api_key=key, timeout=cfg.timeout_s, max_retries=1) if key else None
        )

    @property
    def ready(self) -> bool:
        return self.client is not None

    def _encode(self, img: Image.Image) -> str:
        img = img.copy()
        img.thumbnail((self.cfg.max_side_px, self.cfg.max_side_px))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        return base64.b64encode(buf.getvalue()).decode()

    async def describe(self, img: Image.Image) -> tuple[dict[str, Any], float]:
        if not self.client:
            raise VisionError(f"clé API absente : renseigne {self.cfg.api_key_env} dans .env")
        t0 = time.perf_counter()
        try:
            resp = await self.client.chat.completions.create(
                model=self.cfg.model,
                temperature=self.cfg.temperature,
                max_tokens=self.cfg.max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.cfg.prompt.strip()},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{self._encode(img)}"}},
                    ],
                }],
                extra_body={"chat_template_kwargs": {"enable_thinking": self.cfg.thinking}},
            )
        except Exception as exc:  # délai dépassé, 429, modèle indisponible…
            raise VisionError(f"{type(exc).__name__} : {exc}") from exc
        return parse_fiche(resp.choices[0].message.content or ""), time.perf_counter() - t0


def parse_fiche(text: str) -> dict[str, Any]:
    """Extrait l'objet JSON de la réponse, même entouré de texte ou d'un bloc de code Markdown."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise VisionError("réponse du modèle illisible (pas de JSON)")
    try:
        # Un JSON valide qui commence par « { » et finit par « } » est forcément un objet.
        return json.loads(text[start:end + 1])
    except ValueError as exc:
        raise VisionError("réponse du modèle illisible (JSON invalide)") from exc
