"""Twilio bridge — direct Connect-Stream design (no self-dialing bot-leg).

Architecture:
    - Inbound user call  → <Connect><Stream url=/stream/{pair}/user>
    - Tool dial_contact  → outbound leg to target number → <Connect><Stream url=/stream/{pair}/target>
    - Server mixes audio between user/target/TTS; STT listens to user (+ target when bridged)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from .session import Mode, Phase

logger = logging.getLogger("bridge.twilio")

router = APIRouter()


def _twiml(resp: VoiceResponse) -> Response:
    return Response(content=str(resp), media_type="application/xml")


def _twilio_client() -> TwilioClient:
    return TwilioClient(
        os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
    )


def _base_url(request: Request) -> str:
    cfg = request.app.state.config["service"]
    return cfg["base_url"].rstrip("/") + cfg["path_prefix"]


def _ws_base(request: Request) -> str:
    base = _base_url(request).replace("https://", "wss://").replace("http://", "ws://")
    return base


def _connect_stream_twiml(request: Request, pair_id: str, role: str) -> VoiceResponse:
    """TwiML that opens a bidirectional Media Stream to us. `<Connect>` takes
    over the call audio — we hear the caller and can inject TTS back."""
    vr = VoiceResponse()
    connect = Connect()
    stream = Stream(
        url=f"{_ws_base(request)}/twilio/stream/{pair_id}/{role}",
        name=f"{role}-{pair_id}",
    )
    stream.parameter(name="pair_id", value=pair_id)
    stream.parameter(name="role", value=role)
    connect.append(stream)
    vr.append(connect)
    return vr


@router.post("/twilio/voice-inbound")
async def voice_inbound(
    request: Request,
    From: str = Form(default=""),
    To: str = Form(default=""),
    CallSid: str = Form(default=""),
):
    """Inbound owner-call — opens a session and streams user audio to our WS."""
    from brain.auth import is_owner_caller
    from brain.cost import CostMeter

    cfg_cost = request.app.state.config["cost"]
    meter = CostMeter(
        rates=cfg_cost["rates"],
        cap_usd=cfg_cost["per_call_cap_usd"],
        warn_ratio=cfg_cost["warn_ratio"],
        hangup_ratio=cfg_cost["hangup_ratio"],
    )
    store = request.app.state.sessions
    sess = store.new(caller_id=From, cost_meter=meter)
    sess.phase = Phase.GREETING
    if CallSid:
        sess.add_leg("user", CallSid)
        store.bind_call(sess.pair_id, CallSid)

    auth_cfg = request.app.state.config["auth"]
    whitelist = auth_cfg["owner_whitelist"]
    sess.is_owner = is_owner_caller(From, whitelist)
    sess.authed = sess.is_owner
    # Force default language (DE for owner) so TTS does not wander on short
    # STT utterances. Agent can still switch on explicit command.
    sess.last_language = auth_cfg.get("default_language", "de")

    logger.info(
        json.dumps(
            {
                "event": "inbound",
                "pair_id": sess.pair_id,
                "from": From,
                "call_sid": CallSid,
                "owner": sess.is_owner,
            }
        )
    )

    return _twiml(_connect_stream_twiml(request, sess.pair_id, "user"))


@router.post("/twilio/voice-target-join")
async def voice_target_join(request: Request, CallSid: str = Form(default="")):
    """TwiML answered by an outbound target call — connects target's audio to our WS."""
    pair_id = request.query_params.get("pair_id", "")
    store = request.app.state.sessions
    sess = store.get(pair_id)
    if not sess:
        vr = VoiceResponse()
        vr.hangup()
        return _twiml(vr)
    if CallSid:
        sess.add_leg("target", CallSid)
        store.bind_call(sess.pair_id, CallSid)
    logger.info(
        json.dumps({"event": "target_answer", "pair_id": pair_id, "call_sid": CallSid})
    )
    return _twiml(_connect_stream_twiml(request, sess.pair_id, "target"))


@router.post("/twilio/outbound-dial")
async def outbound_dial(
    request: Request, pair_id: str = Form(...), target_e164: str = Form(...)
):
    """Called by dial_contact tool. Creates an outbound leg that streams its
    audio back to us on /stream/{pair}/target."""
    store = request.app.state.sessions
    sess = store.get(pair_id)
    if not sess:
        return Response(
            content='{"error":"no such pair"}',
            media_type="application/json",
            status_code=404,
        )

    from_num = os.environ["TWILIO_NUMBER"]
    target_url = f"{_base_url(request)}/twilio/voice-target-join?pair_id={pair_id}"
    try:
        client = _twilio_client()
        call = client.calls.create(
            to=target_e164,
            from_=from_num,
            url=target_url,
            method="POST",
            timeout=30,
            status_callback=f"{_base_url(request)}/twilio/call-status",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
    except Exception as exc:
        logger.error(
            json.dumps(
                {"event": "outbound_dial_failed", "pair_id": pair_id, "err": str(exc)}
            )
        )
        return Response(
            content=json.dumps({"ok": False, "error": str(exc)}),
            media_type="application/json",
            status_code=500,
        )

    sess.phase = Phase.DIALING
    logger.info(
        json.dumps(
            {
                "event": "outbound_dial",
                "pair_id": pair_id,
                "to": target_e164,
                "sid": call.sid,
            }
        )
    )
    return Response(
        content=json.dumps({"ok": True, "call_sid": call.sid}),
        media_type="application/json",
    )


@router.post("/twilio/call-status")
async def call_status(request: Request):
    form = await request.form()
    data = {k: str(v) for k, v in form.items()}
    logger.info(json.dumps({"event": "call_status", **data}))
    return Response(status_code=200)


# Legacy endpoint kept returning <Hangup> so any stale reference self-terminates
@router.post("/twilio/voice-bot-join")
async def voice_bot_join_deprecated(request: Request):
    vr = VoiceResponse()
    vr.hangup()
    return _twiml(vr)


@router.post("/twilio/conference-events")
async def conference_events_deprecated(request: Request):
    return Response(status_code=200)


@router.websocket("/twilio/stream/{pair_id}/{role}")
async def stream_ws(ws: WebSocket, pair_id: str, role: str):
    await ws.accept()
    store = ws.app.state.sessions
    sess = store.get(pair_id)
    if not sess:
        await ws.close(code=4404)
        return

    from .session_runner import run_stream_leg

    try:
        await run_stream_leg(ws, sess, role, ws.app.state)
    except WebSocketDisconnect:
        logger.info(
            json.dumps({"event": "ws_disconnect", "pair_id": pair_id, "role": role})
        )
    except Exception:
        logger.exception('"stream error"')
    finally:
        sess.mark_leg_left(role)
        # When the user leg leaves, end the session
        if role == "user":
            sess.end()
