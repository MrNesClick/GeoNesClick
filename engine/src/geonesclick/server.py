"""Moteur du coach : serveur local (FastAPI + WebSocket) qui orchestre capture → N1 local → N2 distant.

Protocole WebSocket (/ws), messages JSON poussés vers l'interface :
  state          état des services (capture, StreetCLIP, vision) et niveau d'aide par défaut
  capture        nouvelle capture : id, miniature (data URL JPEG), durée
  streetclip     niveau 1 : top des pays (local)
  vision_pending niveau 2 en cours (modèle distant)
  vision         niveau 2 : fiche d'indices
  vision_error   niveau 2 en échec
  error          capture impossible
Déclencheurs : POST /capture (bouton de l'interface) ou socket Unix (raccourci GNOME, voir trigger.py).
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from PIL import Image

from .capture import CaptureError, CaptureService, apply_crop_and_masks, save_png
from .config import Config, load_config
from .notify import Notifier
from .paths import SOCKET_PATH
from .streetclip import StreetClip
from .vision import VisionClient, VisionError

THUMB_SIDE = 720


def data_url(img: Image.Image, side: int = THUMB_SIDE) -> str:
    img = img.copy()
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


class Engine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.notifier = Notifier(cfg.capture.notify, cfg.capture.sound)
        self.capture = CaptureService(on_state=self._on_capture_state, source=cfg.capture.source)
        self.capture_message = "démarrage du partage d'écran…"
        self.capture_starting = True  # sélecteur GNOME éventuellement ouvert : ni actif ni coupé
        self.streetclip: StreetClip | None = None
        self.streetclip_message = "chargement du modèle…"
        self.vision = VisionClient(cfg.vision)
        self.gpu_lock = asyncio.Lock()
        # Références vers les tâches du niveau 2 : sans elles, asyncio peut les libérer en cours de route.
        self.background: set[asyncio.Task] = set()

    # --- diffusion -------------------------------------------------------------------------
    def state(self) -> dict[str, Any]:
        return {
            "type": "state",
            "capture": {
                "alive": self.capture.alive,
                "starting": self.capture_starting,
                "message": self.capture_message,
            },
            "streetclip": {"ready": self.streetclip is not None, "message": self.streetclip_message},
            "vision": {
                "enabled": self.cfg.vision.enabled,
                "ready": self.vision.ready,
                "model": self.cfg.vision.model,
            },
            "level": self.cfg.coach.default_level,
        }

    async def broadcast(self, message: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)

    def _on_capture_state(self, alive: bool, message: str, interrupted: bool) -> None:
        """Appelé depuis le thread GLib : on repasse dans la boucle asyncio."""
        self.capture_message = message
        self.capture_starting = False
        if interrupted:
            self.notifier.send("Partage d'écran interrompu", "Relance-le depuis la fenêtre du coach.", error=True)
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(self.state()), self.loop)

    # --- cycle de vie ----------------------------------------------------------------------
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.capture.start()
        if self.cfg.streetclip.enabled:
            try:
                self.streetclip = await asyncio.to_thread(StreetClip, self.cfg.streetclip)
                self.streetclip_message = f"prêt ({self.streetclip.device})"
            except Exception as exc:
                self.streetclip_message = f"indisponible : {exc}"
        else:
            self.streetclip_message = "désactivé"
        await self.broadcast(self.state())

    async def stop(self) -> None:
        await asyncio.to_thread(self.capture.stop)

    # --- analyse ---------------------------------------------------------------------------
    async def analyse(self) -> dict[str, Any]:
        capture_id = f"{datetime.now():%Y%m%d-%H%M%S}-{time.time_ns() % 1000:03d}"
        t0 = time.perf_counter()
        try:
            frame = await asyncio.to_thread(self.capture.grab)
        except CaptureError as exc:
            await asyncio.to_thread(self.notifier.send, "Capture impossible", str(exc), error=True)
            await self.broadcast({"type": "error", "message": str(exc)})
            return {"ok": False, "error": str(exc)}

        view = apply_crop_and_masks(frame, self.cfg.capture.crop, self.cfg.capture.masks)
        saved = None
        if self.cfg.capture.save_to_disk:
            saved = await asyncio.to_thread(save_png, view, self.cfg.capture.path, f"capture-{capture_id}")
        capture_ms = (time.perf_counter() - t0) * 1000
        await asyncio.to_thread(self.notifier.send, "Capture prise", f"{capture_ms:.0f} ms", image=saved)
        await self.broadcast({
            "type": "capture", "id": capture_id, "at": datetime.now().isoformat(timespec="seconds"),
            "thumbnail": await asyncio.to_thread(data_url, view), "ms": round(capture_ms),
        })

        if self.cfg.vision.enabled:  # niveau 2 en parallèle : il est lent, on ne l'attend pas
            task = asyncio.create_task(self._vision(capture_id, view))
            self.background.add(task)
            task.add_done_callback(self.background.discard)

        if self.streetclip:
            try:
                async with self.gpu_lock:
                    scores, ms = await asyncio.to_thread(self.streetclip.predict, view)
            except Exception as exc:  # mémoire GPU saturée, pilote…
                await self.broadcast({"type": "error", "message": f"Niveau 1 indisponible : {exc}"})
                return {"ok": False, "error": str(exc)}
            await self.broadcast({
                "type": "streetclip", "id": capture_id, "ms": round(ms),
                "scores": [s.__dict__ for s in scores],
            })
        return {"ok": True, "id": capture_id}

    async def _vision(self, capture_id: str, view: Image.Image) -> None:
        await self.broadcast({"type": "vision_pending", "id": capture_id, "model": self.cfg.vision.model})
        try:
            fiche, seconds = await self.vision.describe(view)
            await self.broadcast({
                "type": "vision", "id": capture_id, "model": self.cfg.vision.model,
                "seconds": round(seconds, 1), "fiche": fiche,
            })
        except VisionError as exc:
            await self.broadcast({"type": "vision_error", "id": capture_id, "error": str(exc)})


async def _unix_trigger(engine: Engine) -> asyncio.AbstractServer:
    """Socket Unix réservé à l'utilisateur (0600) : reçoit « capture » depuis le raccourci GNOME."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            cmd = (await asyncio.wait_for(reader.readline(), 2)).decode(errors="replace").strip()
            if cmd == "capture":
                result = await engine.analyse()
                writer.write((f"OK {result['id']}" if result["ok"] else f"ERR {result['error']}").encode() + b"\n")
            else:
                writer.write(b"ERR commande inconnue\n")
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()

    SOCKET_PATH.unlink(missing_ok=True)
    old_umask = os.umask(0o177)
    try:
        return await asyncio.start_unix_server(handle, path=str(SOCKET_PATH))
    finally:
        os.umask(old_umask)


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or load_config()
    engine = Engine(cfg)
    allowed = set(cfg.server.allowed_origins)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        trigger = await _unix_trigger(engine)
        start_task = asyncio.create_task(engine.start())
        try:
            yield
        finally:
            start_task.cancel()
            trigger.close()
            SOCKET_PATH.unlink(missing_ok=True)
            await engine.stop()

    app = FastAPI(title="GeoNesClick", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    # Contre le « DNS rebinding » : un domaine piégé qui pointerait vers 127.0.0.1 garde son propre Host.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        # Un site web ouvert dans le navigateur pourrait viser 127.0.0.1 : on refuse toute origine inconnue.
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed:
            return JSONResponse({"error": "origine refusée"}, status_code=403)
        response = await call_next(request)
        if origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return response

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return engine.state()

    @app.post("/capture")
    async def capture() -> dict[str, Any]:
        return await engine.analyse()

    @app.post("/capture/restart")
    async def restart() -> dict[str, Any]:
        engine.capture_message = "relance du partage d'écran…"
        engine.capture_starting = True
        await engine.broadcast(engine.state())
        await asyncio.to_thread(engine.capture.restart)
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        if websocket.headers.get("origin") not in allowed:
            await websocket.close(code=1008)  # violation de politique
            return
        await websocket.accept()
        engine.clients.add(websocket)
        try:
            await websocket.send_json(engine.state())
            while True:
                await websocket.receive_text()  # l'interface n'envoie rien pour l'instant
        except WebSocketDisconnect:
            pass
        finally:
            engine.clients.discard(websocket)

    return app


def main() -> None:
    import uvicorn

    cfg = load_config()
    with suppress(KeyboardInterrupt):
        uvicorn.run(create_app(cfg), host=cfg.server.host, port=cfg.server.port, log_level="info")
