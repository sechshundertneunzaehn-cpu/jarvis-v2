"""µ-law 8kHz codec + paced frame emitter + jitter-buffer."""
from __future__ import annotations

import asyncio
import audioop
import base64
import time
from collections import deque
from dataclasses import dataclass
from typing import AsyncIterator, Iterable


FRAME_BYTES = 160  # 20ms of µ-law 8kHz
FRAME_SECONDS = 0.020
SAMPLE_RATE = 8000


def pcm16_to_mulaw(pcm16: bytes) -> bytes:
    if not pcm16:
        return b""
    return audioop.lin2ulaw(pcm16, 2)


def mulaw_to_pcm16(mulaw: bytes) -> bytes:
    if not mulaw:
        return b""
    return audioop.ulaw2lin(mulaw, 2)


def chunk_frames(data: bytes, size: int = FRAME_BYTES) -> Iterable[bytes]:
    for i in range(0, len(data), size):
        frame = data[i : i + size]
        if len(frame) < size:
            frame = frame + b"\xff" * (size - len(frame))  # µ-law silence = 0xFF
        yield frame


def mulaw_silence(frames: int = 1) -> bytes:
    return b"\xff" * (FRAME_BYTES * frames)


@dataclass
class PacedSender:
    """Monotonic-pacing emitter — ensures 20ms cadence even with jitter in source."""

    send_fn: callable  # async, takes one frame
    frame_seconds: float = FRAME_SECONDS

    async def send_stream(self, data_chunks: AsyncIterator[bytes]) -> None:
        next_tick = time.monotonic()
        pending = bytearray()
        async for chunk in data_chunks:
            if not chunk:
                continue
            pending.extend(chunk)
            while len(pending) >= FRAME_BYTES:
                frame = bytes(pending[:FRAME_BYTES])
                del pending[:FRAME_BYTES]
                now = time.monotonic()
                sleep_for = next_tick - now
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                await self.send_fn(frame)
                next_tick += self.frame_seconds
                # If we fell more than 200ms behind, resync rather than spam
                if next_tick < now - 0.2:
                    next_tick = time.monotonic()
        if pending:
            frame = bytes(pending) + b"\xff" * (FRAME_BYTES - len(pending))
            await self.send_fn(frame)


class JitterBuffer:
    """Fixed-delay jitter buffer for inbound µ-law frames."""

    def __init__(self, target_ms: int = 100) -> None:
        self.target_frames = max(1, target_ms // 20)
        self._q: deque[bytes] = deque()

    def push(self, frame: bytes) -> None:
        self._q.append(frame)

    def pop(self) -> bytes | None:
        if len(self._q) >= self.target_frames:
            return self._q.popleft()
        return None

    def drain(self) -> bytes:
        out = b"".join(self._q)
        self._q.clear()
        return out

    def depth(self) -> int:
        return len(self._q)


def twilio_media_payload_to_mulaw(payload_b64: str) -> bytes:
    return base64.b64decode(payload_b64)


def mulaw_to_twilio_media_payload(mulaw: bytes) -> str:
    return base64.b64encode(mulaw).decode("ascii")
