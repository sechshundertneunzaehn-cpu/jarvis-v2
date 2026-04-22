"""Deepgram Nova-3 streaming STT client (mulaw 8kHz multi-lang)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Awaitable, Callable, Optional
from urllib.parse import urlencode

import websockets

logger = logging.getLogger("stt.deepgram")


class DeepgramSTT:
    """Streaming STT wrapper around Deepgram's WS endpoint."""

    URL = "wss://api.deepgram.com/v1/listen"

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._closed = False
        self._on_final: Optional[Callable[[str, Optional[str]], Awaitable[None]]] = None
        self._on_speech_started: Optional[Callable[[], Awaitable[None]]] = None
        self._send_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=500)
        self._connect_lock = asyncio.Lock()

    def _qs(self) -> str:
        params = {
            "model": self.cfg.get("model", "nova-3"),
            "language": self.cfg.get("language", "multi"),
            "encoding": self.cfg.get("encoding", "mulaw"),
            "sample_rate": self.cfg.get("sample_rate", 8000),
            "interim_results": "true" if self.cfg.get("interim_results", True) else "false",
            "utterance_end_ms": self.cfg.get("utterance_end_ms", 1000),
            "endpointing": self.cfg.get("endpointing", 300),
            "vad_events": "true" if self.cfg.get("vad_events", True) else "false",
            "smart_format": "true" if self.cfg.get("smart_format", True) else "false",
            "channels": 1,
        }
        return urlencode(params)

    async def _connect(self) -> None:
        if self._ws and not self._ws.closed:
            return
        async with self._connect_lock:
            if self._ws and not self._ws.closed:
                return
            url = f"{self.URL}?{self._qs()}"
            self._ws = await websockets.connect(
                url,
                extra_headers={"Authorization": f"Token {self.api_key}"},
                max_size=2**23,
                ping_interval=20,
                ping_timeout=20,
            )
            logger.info('"deepgram stt connected"')

    async def run(
        self,
        on_final: Callable[[str, Optional[str]], Awaitable[None]],
        on_speech_started: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        """Main pump — connects + consumes events until .close() is called."""
        self._on_final = on_final
        self._on_speech_started = on_speech_started
        await self._connect()
        recv_task = asyncio.create_task(self._recv_loop())
        send_task = asyncio.create_task(self._send_loop())
        try:
            await asyncio.gather(recv_task, send_task)
        except asyncio.CancelledError:
            pass

    async def _send_loop(self) -> None:
        while not self._closed:
            try:
                chunk = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if chunk is None:
                break
            if self._ws and not self._ws.closed:
                try:
                    await self._ws.send(chunk)
                except websockets.ConnectionClosed:
                    logger.warning('"deepgram send: connection closed"')
                    return

    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    evt = json.loads(raw)
                except Exception:
                    continue
                await self._dispatch(evt)
        except websockets.ConnectionClosed:
            logger.info('"deepgram stt ws closed"')

    async def _dispatch(self, evt: dict) -> None:
        kind = evt.get("type")
        if kind == "Results":
            channel = evt.get("channel", {})
            alts = channel.get("alternatives", [])
            if not alts:
                return
            transcript = alts[0].get("transcript", "")
            is_final = bool(evt.get("is_final"))
            speech_final = bool(evt.get("speech_final"))
            lang = alts[0].get("languages", [None])[0] if alts[0].get("languages") else None
            if is_final and speech_final and transcript.strip():
                if self._on_final:
                    await self._on_final(transcript, lang)
        elif kind == "UtteranceEnd":
            logger.debug('"utterance_end"')
        elif kind == "SpeechStarted":
            logger.debug('"speech_started"')
            if self._on_speech_started:
                try:
                    await self._on_speech_started()
                except Exception:
                    logger.exception('"speech_started handler failed"')

    async def feed(self, mulaw_chunk: bytes) -> None:
        if self._closed:
            return
        try:
            self._send_queue.put_nowait(mulaw_chunk)
        except asyncio.QueueFull:
            logger.warning('"stt feed queue full, dropping"')

    async def close(self) -> None:
        self._closed = True
        try:
            await self._send_queue.put(None)
        except Exception:
            pass
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
            try:
                await self._ws.close()
            except Exception:
                pass
