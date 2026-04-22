import asyncio
import time

import pytest

from bridge.audio import (
    FRAME_BYTES,
    FRAME_SECONDS,
    JitterBuffer,
    PacedSender,
    chunk_frames,
    mulaw_silence,
    mulaw_to_pcm16,
    mulaw_to_twilio_media_payload,
    pcm16_to_mulaw,
    twilio_media_payload_to_mulaw,
)


def test_frame_constants():
    assert FRAME_BYTES == 160
    assert abs(FRAME_SECONDS - 0.020) < 1e-9


def test_silence_is_0xff():
    s = mulaw_silence(2)
    assert len(s) == 320
    assert all(b == 0xFF for b in s)


def test_chunk_frames_pads_last():
    data = b"\x00" * 161  # 1 byte over one frame
    frames = list(chunk_frames(data))
    assert len(frames) == 2
    assert len(frames[0]) == 160
    assert len(frames[1]) == 160
    assert frames[1][1] == 0xFF


def test_pcm_roundtrip_shape():
    pcm = b"\x00\x01" * 80  # 80 samples of pcm16 -> 80 bytes mulaw
    mulaw = pcm16_to_mulaw(pcm)
    assert len(mulaw) == 80
    back = mulaw_to_pcm16(mulaw)
    assert len(back) == 160  # mulaw 80 -> pcm16 160 bytes


def test_pcm_empty():
    assert pcm16_to_mulaw(b"") == b""
    assert mulaw_to_pcm16(b"") == b""


def test_b64_roundtrip():
    payload = b"\xff\x00\x7f" * 10
    enc = mulaw_to_twilio_media_payload(payload)
    assert isinstance(enc, str)
    assert twilio_media_payload_to_mulaw(enc) == payload


def test_jitter_buffer_warmup():
    jb = JitterBuffer(target_ms=100)  # 5 frames warmup
    for i in range(4):
        jb.push(b"\x00" * 160)
    assert jb.pop() is None  # below target depth
    jb.push(b"\x00" * 160)
    assert jb.pop() is not None
    assert jb.depth() == 4


def test_jitter_buffer_drain():
    jb = JitterBuffer(target_ms=40)
    jb.push(b"a" * 160)
    jb.push(b"b" * 160)
    d = jb.drain()
    assert len(d) == 320
    assert jb.depth() == 0


@pytest.mark.asyncio
async def test_paced_sender_timing():
    sent: list[tuple[float, bytes]] = []

    async def send(frame: bytes):
        sent.append((time.monotonic(), frame))

    ps = PacedSender(send_fn=send)

    async def chunks():
        yield b"\x00" * (FRAME_BYTES * 5)

    t0 = time.monotonic()
    await ps.send_stream(chunks())
    elapsed = time.monotonic() - t0
    assert len(sent) == 5
    # 5 frames of 20ms each: ≥ 80ms cadence; allow slack
    assert elapsed >= 0.06
