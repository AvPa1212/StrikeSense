"""StrikeSense server: sample source -> kick detector -> features -> network -> dashboard.

Run:  uvicorn app:app --port 8000        (SOURCE=sim by default, no hardware needed)
      SOURCE=serial SERIAL_PORT=COM5 uvicorn app:app --port 8000
"""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import coach
import config
from config import CONTEXT_PATH
from features import KickDetector, extract_features
from simulator import PRIORS, SimSource
from store import make_store
from technique import IMPORTANCE, LABELS, SCORE_METRICS, TECHNIQUES, TechniqueModel, retrain_from_labeled

LEVELS = {"pro": 0.5, "good": 1.0, "amateur": 1.7}


class Engine:
    def __init__(self) -> None:
        self.model = TechniqueModel()
        self.model.load_or_train()
        self.store = make_store()
        self.detector = KickDetector()
        self.clients: set[WebSocket] = set()
        self.target = "auto"
        self.session = time.strftime("%Y%m%d-%H%M%S")
        self.coach_cache: dict[int, dict] = {}
        self.source = None
        self.rate_hz = 0.0
        self._count = 0
        self._count_t = time.monotonic()
        self.task: asyncio.Task | None = None
        self.samples_total = 0

    def open_source(self) -> None:
        if config.SOURCE == "serial":
            from serial_source import SerialSource
            self.source = SerialSource(config.SERIAL_PORT, config.BAUD)
        else:
            import os
            self.source = SimSource(auto=os.getenv("SIM_AUTO", "1") == "1")

    def status(self) -> dict:
        return {
            "type": "status",
            "source": self.source.name if self.source else "none",
            "rate_hz": round(self.rate_hz),
            "bad_packets": getattr(self.source, "bad_packets", 0),
            "recording": self.detector.recording,
            "target": self.target,
            "session": self.session,
            "high_g": config.ACCEL_RANGE_G > 100,
            "accel_range_g": config.ACCEL_RANGE_G,
            "gyro_range_dps": config.GYRO_RANGE_DPS,
            "real_kicks_in_model": self.model.n_real,
            "gemini": bool(config.GEMINI_API_KEY),
            "elevenlabs": bool(config.ELEVENLABS_API_KEY),
            "db": self.store.name,
        }

    async def broadcast(self, msg: dict) -> None:
        if not self.clients:
            return
        data = json.dumps(msg)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def handle_window(self, win: dict) -> None:
        feat = extract_features(win["t"], win["a"], win["g"], win["f"])
        if feat is None:
            await self.broadcast({"type": "ignored"})
            return
        pred = self.model.classify(feat)
        technique = pred["technique"] if self.target == "auto" else self.target
        score = self.model.score(feat, technique)
        r3 = lambda x: np.round(x, 3).tolist()
        kick = {
            "ts": time.time(), "session": self.session, "target": self.target,
            "technique": technique, "predicted": pred["technique"],
            "confidence": pred["confidence"], "overall": score["overall"],
            "features": feat, "score": score, "probs": pred["probs"], "label": None,
            "window": {"t": r3(win["t"]), "a": r3(win["a"]), "g": r3(win["g"]),
                       "f": np.round(win["f"]).astype(int).tolist()},
        }
        kick["id"] = self.store.add_kick(kick)
        summary = {k: v for k, v in kick.items() if k != "window"}
        await self.broadcast({"type": "kick", "kick": summary})

    async def pump(self) -> None:
        while True:
            await asyncio.sleep(0.04)
            samples = self.source.drain()
            now = time.monotonic()
            if samples:
                self._count += len(samples)
                self.samples_total += len(samples)
                for s in samples:
                    win = self.detector.push(s)
                    if win is not None:
                        await self.handle_window(win)
                await self.broadcast({
                    "type": "samples",
                    "t": [round(s.t, 3) for s in samples],
                    "a": [[round(x, 2) for x in s.a] for s in samples],
                    "g": [[round(x, 1) for x in s.g] for s in samples],
                    "f": [list(s.f) for s in samples],
                })
                if self.store.name == "postgres":
                    await asyncio.to_thread(self.store.insert_samples, self.session, time.time(), samples)
            if now - self._count_t >= 1.0:
                self.rate_hz = self._count / (now - self._count_t)
                self._count, self._count_t = 0, now
                await self.broadcast(self.status())


engine: Engine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    engine = Engine()
    engine.open_source()
    engine.task = asyncio.create_task(engine.pump())
    yield
    engine.task.cancel()
    engine.source.close()


app = FastAPI(title="StrikeSense", lifespan=lifespan)


class TargetIn(BaseModel):
    technique: str


class LabelIn(BaseModel):
    technique: str | None = None


@app.get("/api/status")
def get_status():
    return engine.status()


@app.get("/api/techniques")
def get_techniques():
    return {
        "techniques": [{"key": t, "label": LABELS[t]} for t in TECHNIQUES],
        "importance": [{"name": n, "weight": w, "why": why} for n, w, why in IMPORTANCE],
        "metrics": {k: {"label": v[0], "unit": v[1], "weight": v[2], "needs_high_g": v[3]}
                    for k, v in SCORE_METRICS.items()},
        "benchmarks": engine.model.bench,
    }


@app.get("/api/kicks")
def list_kicks(all_sessions: bool = False, limit: int = 200):
    return engine.store.list_kicks(None if all_sessions else engine.session, limit)


@app.get("/api/kicks/{kick_id}")
def get_kick(kick_id: int):
    k = engine.store.get_kick(kick_id)
    if not k:
        raise HTTPException(404, "No kick with that id")
    return k


@app.get("/api/kicks/{kick_id}/coach")
async def get_coach(kick_id: int):
    if kick_id in engine.coach_cache:
        return engine.coach_cache[kick_id]
    k = engine.store.get_kick(kick_id)
    if not k:
        raise HTTPException(404, "No kick with that id")
    fb = await coach.feedback(k)
    engine.coach_cache[kick_id] = fb
    return fb


@app.get("/api/kicks/{kick_id}/voice")
async def get_voice(kick_id: int):
    fb = await get_coach(kick_id)
    audio = await coach.speak(fb["text"])
    if audio is None:
        return JSONResponse({"detail": "Voice unavailable. Set ELEVENLABS_API_KEY."}, status_code=501)
    return Response(audio, media_type="audio/mpeg")


@app.post("/api/kicks/{kick_id}/label")
def label_kick(kick_id: int, body: LabelIn):
    if body.technique is not None and body.technique not in TECHNIQUES:
        raise HTTPException(400, f"technique must be one of {TECHNIQUES}")
    engine.store.set_label(kick_id, body.technique)
    return {"ok": True}


@app.post("/api/model/retrain")
def retrain():
    labeled = engine.store.labeled()
    if not labeled:
        raise HTTPException(400, "Label at least one real kick first.")
    return retrain_from_labeled(engine.model, labeled)


@app.post("/api/target")
def set_target(body: TargetIn):
    if body.technique != "auto" and body.technique not in TECHNIQUES:
        raise HTTPException(400, f"technique must be auto or one of {TECHNIQUES}")
    engine.target = body.technique
    return {"target": engine.target}


@app.post("/api/session/new")
def new_session():
    engine.session = time.strftime("%Y%m%d-%H%M%S")
    engine.coach_cache.clear()
    return {"session": engine.session}


@app.post("/api/sim/kick")
def sim_kick(technique: str | None = Query(None), level: str = Query("good")):
    if engine.source.name != "simulator":
        raise HTTPException(400, "Simulator is not the active source.")
    if technique and technique not in PRIORS:
        raise HTTPException(400, f"technique must be one of {list(PRIORS)}")
    truth = engine.source.trigger(technique, LEVELS.get(level, 1.0))
    return {"queued": truth["technique"]}


@app.get("/api/context")
def get_context():
    if CONTEXT_PATH.exists():
        return json.loads(CONTEXT_PATH.read_text())
    return JSONResponse({"detail": "Run python statsbomb_context.py to build this."}, status_code=404)


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    engine.clients.add(websocket)
    await websocket.send_text(json.dumps(engine.status()))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        engine.clients.discard(websocket)


_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
