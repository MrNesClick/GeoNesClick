"""Clue sheet from a remote vision model (level 2, asynchronous)."""

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
        """Clue sheet of the whole view."""
        return await self.ask(img, self.cfg.prompt, self.cfg.model, self.cfg.max_tokens)

    async def ask(self, img: Image.Image, prompt: str, model: str, max_tokens: int) -> tuple[dict[str, Any], float]:
        """One image, one instruction: returns the JSON object of the answer and the duration of the call."""
        if not self.client:
            raise VisionError("clé API absente : saisis-la dans Réglages › Analyse")
        t0 = time.perf_counter()
        try:
            resp = await self.client.chat.completions.create(
                model=model,
                temperature=self.cfg.temperature,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt.strip()},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{self._encode(img)}"}},
                    ],
                }],
                extra_body={"chat_template_kwargs": {"enable_thinking": self.cfg.thinking}},
            )
        except Exception as exc:  # timeout, 429, model unavailable…
            raise VisionError(f"{type(exc).__name__} : {exc}") from exc
        return parse_fiche(resp.choices[0].message.content or ""), time.perf_counter() - t0

    async def list_models(self) -> list[str]:
        """Identifiers of the available models (the API's public list)."""
        if not self.client:
            raise VisionError("clé API absente : saisis-la dans Réglages › Analyse")
        try:
            page = await self.client.models.list()
        except Exception as exc:
            raise VisionError(f"{type(exc).__name__} : {exc}") from exc
        return sorted(m.id for m in page.data)

    async def probe(self, model: str) -> float:
        """Sends a small image to the model: checks that it accepts images and measures its latency."""
        if not self.client:
            raise VisionError("clé API absente : saisis-la dans Réglages › Analyse")
        img = Image.new("RGB", (96, 64), (90, 140, 200))  # plain sky: minimal test
        t0 = time.perf_counter()
        try:
            await self.client.chat.completions.create(
                model=model,
                max_tokens=20,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "De quelle couleur est cette image ? Un mot."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{self._encode(img)}"}},
                    ],
                }],
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except Exception as exc:
            raise VisionError(f"{type(exc).__name__} : {exc}") from exc
        return time.perf_counter() - t0


def parse_fiche(text: str) -> dict[str, Any]:
    """Extracts the JSON object from the answer, even when surrounded by text or a Markdown code block."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise VisionError("réponse du modèle illisible (pas de JSON)")
    try:
        # A valid JSON that starts with "{" and ends with "}" is necessarily an object.
        return json.loads(text[start:end + 1])
    except ValueError as exc:
        raise VisionError("réponse du modèle illisible (JSON invalide)") from exc
