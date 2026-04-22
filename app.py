"""Jarvis v2 — FastAPI main."""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())

from bridge.session import SessionStore  # noqa: E402
from contacts.registry import ContactRegistry  # noqa: E402
from knowledge.store import KnowledgeStore  # noqa: E402


def _setup_logging() -> None:
    log_cfg = CONFIG["log"]
    log_path = Path(log_cfg["path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(log_cfg["level"])
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter(
        '{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":%(message)s}'
    )
    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(sh)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _setup_logging()
    logging.getLogger("jarvis").info('"jarvis-v2 starting"')
    app.state.config = CONFIG
    app.state.sessions = SessionStore()
    app.state.contacts = ContactRegistry(ROOT / "contacts" / "contacts.yaml")
    app.state.knowledge = KnowledgeStore(ROOT / "knowledge")
    app.state.started_at = time.time()
    yield
    logging.getLogger("jarvis").info('"jarvis-v2 stopping"')


app = FastAPI(title="jarvis-v2", lifespan=lifespan)

from bridge.twilio_conf import router as twilio_router  # noqa: E402

app.include_router(twilio_router, prefix="/v2")


@app.get("/v2/health")
async def health(request: Request):
    s = request.app.state
    uptime = time.time() - s.started_at
    stt_cfg = CONFIG["stt"]
    tts_cfg = CONFIG["tts"]
    contact_names = [c.get("name") for c in s.contacts.all()]
    # last_deploy_ts: mtime of the most recently modified source file — good
    # proxy for "when did this build ship" without a separate version file.
    try:
        newest = max(
            (p.stat().st_mtime for p in ROOT.rglob("*.py") if "venv" not in str(p)),
            default=s.started_at,
        )
        last_deploy_ts = round(newest, 1)
    except Exception:
        last_deploy_ts = round(s.started_at, 1)
    return JSONResponse(
        {
            "service": "jarvis-v2",
            "status": "ok",
            "uptime_s": round(uptime, 1),
            "active_calls": s.sessions.active_count(),
            "contacts_loaded": s.contacts.count(),
            "contacts_loaded_names": contact_names,
            "knowledge_docs": s.knowledge.count(),
            "models": {
                "brain": CONFIG["brain"]["primary_model"],
                "stt": CONFIG["stt"]["model"],
                "tts_de": tts_cfg["voices"]["de"],
            },
            "stt_lang": stt_cfg.get("language"),
            "stt_allowed_langs": stt_cfg.get("allowed_langs"),
            "stt_endpointing_ms": stt_cfg.get("endpointing"),
            "stt_post_hold_ms": stt_cfg.get("post_utterance_hold_ms", 0),
            "barge_in_enabled": bool(stt_cfg.get("barge_in", False)),
            "tts_voices": tts_cfg.get("voices", {}),
            "last_deploy_ts": last_deploy_ts,
        }
    )


@app.get("/v2/active-calls")
async def active_calls(request: Request):
    return JSONResponse(request.app.state.sessions.dashboard())


@app.get("/v2/ping")
async def ping():
    return PlainTextResponse("pong")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=CONFIG["service"]["host"],
        port=int(os.environ.get("SERVICE_PORT", CONFIG["service"]["port"])),
        log_level=CONFIG["log"]["level"].lower(),
    )
