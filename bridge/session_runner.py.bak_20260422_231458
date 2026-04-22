"""Per-leg runner: wires STT ↔ Claude ↔ TTS and mixes user/target audio.

Design:
    - Each leg (user, target) has its own WebSocket handler: run_stream_leg.
    - Session holds a shared AudioHub that brokers audio between legs + TTS.
    - Only the user-leg drives the agent (STT → Claude → TTS).
    - Target audio is forwarded to user-leg when sess.phase == BRIDGED and
      from target → STT as secondary input for interpreter mode.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket

import re

from .audio import (
    FRAME_BYTES,
    FRAME_SECONDS,
    mulaw_to_twilio_media_payload,
    twilio_media_payload_to_mulaw,
)
from .session import Phase, Session


_SENTENCE_END = re.compile(r"([\.!\?;…:])\s+|([\.!\?;…])$")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentence-sized chunks for low-latency TTS batching.
    First chunk gets spoken quickly; rest stream in behind.
    """
    text = text.strip()
    if not text:
        return []
    parts: list[str] = []
    last = 0
    for m in _SENTENCE_END.finditer(text):
        end = m.end()
        chunk = text[last:end].strip()
        if chunk:
            parts.append(chunk)
        last = end
    tail = text[last:].strip()
    if tail:
        parts.append(tail)
    return parts

logger = logging.getLogger("bridge.runner")


class AudioHub:
    """Per-session audio broker. Each leg registers its outbound queue; any
    source can publish frames to a named sink ('user', 'target', 'all')."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Optional[bytes]]] = {}
        self._stream_sids: dict[str, str] = {}
        self._lock = asyncio.Lock()

    def flush(self, role: str) -> int:
        """Drain any pending frames for a sink (used for barge-in)."""
        q = self._queues.get(role)
        if not q:
            return 0
        dropped = 0
        while not q.empty():
            try:
                q.get_nowait()
                dropped += 1
            except Exception:
                break
        return dropped

    def register(self, role: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._queues[role] = q
        return q

    def unregister(self, role: str) -> None:
        q = self._queues.pop(role, None)
        if q is not None:
            try:
                q.put_nowait(None)
            except Exception:
                pass
        self._stream_sids.pop(role, None)

    def set_stream_sid(self, role: str, sid: str) -> None:
        self._stream_sids[role] = sid

    def stream_sid(self, role: str) -> Optional[str]:
        return self._stream_sids.get(role)

    async def send(self, role: str, frame: bytes) -> None:
        q = self._queues.get(role)
        if not q:
            return
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            # drop oldest
            try:
                q.get_nowait()
            except Exception:
                pass
            try:
                q.put_nowait(frame)
            except Exception:
                pass

    async def broadcast(self, except_role: str, frame: bytes) -> None:
        for r in list(self._queues):
            if r == except_role:
                continue
            await self.send(r, frame)


async def run_stream_leg(
    ws: WebSocket, sess: Session, role: str, app_state
) -> None:
    """Main WS pump for one leg (user|target)."""
    hub: AudioHub = getattr(sess, "audio_hub", None) or AudioHub()
    sess.audio_hub = hub  # type: ignore[attr-defined]

    out_queue = hub.register(role)

    # Lazy-init STT/TTS/Agent once (shared across legs of a session)
    first_time = not hasattr(sess, "agent")
    if first_time and role == "user":
        await _init_ai_pipeline(sess, app_state, hub)

    # Outbound pump for this leg — paced at 20ms/frame cadence so Twilio
    # doesn't overflow its jitter buffer when we burst-dump a TTS response.
    async def outbound_pump():
        import asyncio as _a
        import time as _t

        next_tick = _t.monotonic()
        while True:
            frame = await out_queue.get()
            if frame is None:
                return
            sid = hub.stream_sid(role)
            if not sid:
                continue
            # Drift-compensated pacing
            now = _t.monotonic()
            sleep_for = next_tick - now
            if sleep_for > 0:
                await _a.sleep(sleep_for)
            elif sleep_for < -0.2:
                # Fell behind by >200ms — resync to avoid bursting forever
                next_tick = _t.monotonic()
            payload = mulaw_to_twilio_media_payload(frame)
            try:
                await ws.send_text(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": sid,
                            "media": {"payload": payload},
                        }
                    )
                )
            except Exception:
                return
            next_tick += FRAME_SECONDS

    out_task = asyncio.create_task(outbound_pump())

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            ev = data.get("event")
            if ev == "start":
                sid = data["start"]["streamSid"]
                hub.set_stream_sid(role, sid)
                logger.info(
                    json.dumps(
                        {
                            "event": "stream_start",
                            "pair_id": sess.pair_id,
                            "role": role,
                            "streamSid": sid,
                        }
                    )
                )
                # Greet when user-leg comes up
                if role == "user" and hasattr(sess, "agent"):
                    asyncio.create_task(_greet(sess, hub))
            elif ev == "media":
                payload = data["media"]["payload"]
                mulaw = twilio_media_payload_to_mulaw(payload)
                # User → STT (and → target when bridged)
                if role == "user":
                    stt = getattr(sess, "stt", None)
                    if stt:
                        await stt.feed(mulaw)
                    if sess.phase == Phase.BRIDGED:
                        await hub.send("target", mulaw)
                elif role == "target":
                    # Target → user (always once streaming), → STT only in interpreter mode
                    await hub.send("user", mulaw)
                    if sess.mode.value == "interpreter":
                        stt = getattr(sess, "stt", None)
                        if stt:
                            await stt.feed(mulaw)
                    if sess.phase == Phase.DIALING:
                        sess.phase = Phase.BRIDGED
            elif ev == "stop":
                logger.info(
                    json.dumps(
                        {
                            "event": "stream_stop",
                            "pair_id": sess.pair_id,
                            "role": role,
                        }
                    )
                )
                break
    finally:
        hub.unregister(role)
        out_task.cancel()
        if role == "user":
            # Tear down shared pipeline
            stt = getattr(sess, "stt", None)
            if stt:
                try:
                    await stt.close()
                except Exception:
                    pass
            tts = getattr(sess, "tts", None)
            if tts:
                try:
                    await tts.close()
                except Exception:
                    pass


async def _init_ai_pipeline(sess: Session, app_state, hub: AudioHub) -> None:
    """Instantiate STT/TTS/Agent for a new session (user-leg triggers this)."""
    try:
        from stt.deepgram_ws import DeepgramSTT
        from tts.deepgram_tts import DeepgramTTS
        from brain.claude_agent import ClaudeAgent
    except Exception as exc:
        logger.warning(json.dumps({"event": "degraded_mode", "err": str(exc)}))
        return

    cfg = app_state.config
    stt = DeepgramSTT(cfg["stt"])
    tts = DeepgramTTS(cfg["tts"])
    agent = ClaudeAgent(sess=sess, app_state=app_state, config=cfg["brain"])
    sess.stt = stt  # type: ignore[attr-defined]
    sess.tts = tts  # type: ignore[attr-defined]
    sess.agent = agent  # type: ignore[attr-defined]

    # Jarvis-lite: DE-only, no barge-in, serialized turns.
    stt_cfg = app_state.config["stt"]

    async def _run_turn(text: str) -> None:
        """One serialized user-turn: STT-final → agent → TTS → outbound frames."""
        sess.last_language = "de"  # hard lock
        logger.info(
            json.dumps(
                {
                    "event": "user_said",
                    "pair_id": sess.pair_id,
                    "text": text[:300],
                }
            )
        )
        full_text = ""
        try:
            async for chunk in agent.respond(text, lang="de"):
                full_text += chunk
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('"agent respond failed"')
            return

        if not full_text.strip():
            return

        sentences = _split_sentences(full_text) or [full_text]
        logger.info(
            json.dumps(
                {
                    "event": "assistant_say",
                    "pair_id": sess.pair_id,
                    "text": full_text[:300],
                    "sentences": len(sentences),
                }
            )
        )
        try:
            for sentence in sentences:
                async for frame in tts.stream(sentence, lang="de"):
                    await hub.send("user", frame)
                    if sess.phase == Phase.BRIDGED:
                        await hub.send("target", frame)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('"tts stream failed"')

    async def on_final_transcript(text: str, lang: Optional[str]) -> None:
        if not text.strip():
            return
        # Cancel any still-running turn cleanly before starting a new one.
        prev = getattr(sess, "current_turn_task", None)
        if prev and not prev.done():
            logger.info(
                json.dumps(
                    {
                        "event": "tts_cancelled_for_new_utterance",
                        "pair_id": sess.pair_id,
                    }
                )
            )
            prev.cancel()
            try:
                await prev
            except (asyncio.CancelledError, Exception):
                pass
        # Flush any pending frames from the cancelled turn so they don't mix
        # with the next response.
        hub.flush("user")
        if sess.phase == Phase.BRIDGED:
            hub.flush("target")
        sess.current_turn_task = asyncio.create_task(_run_turn(text))  # type: ignore[attr-defined]

    # Barge-in disabled: no on_speech_started callback registered.
    sess.stt_task = asyncio.create_task(stt.run(on_final_transcript))  # type: ignore[attr-defined]


async def _greet(sess: Session, hub: AudioHub) -> None:
    tts = getattr(sess, "tts", None)
    if not tts:
        return
    if sess.is_owner:
        text = "Hallo Askin, hier ist Jarvis. Wie kann ich helfen?"
    else:
        text = "Hallo. Wer spricht bitte?"
    try:
        async for frame in tts.stream(text, lang="de"):
            await hub.send("user", frame)
    except Exception:
        logger.exception('"greet failed"')
