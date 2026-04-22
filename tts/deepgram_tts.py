"""Deepgram Aura-2 streaming TTS (mulaw 8kHz). Language-aware voice selection."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import AsyncIterator, Optional

import httpx

from bridge.audio import FRAME_BYTES

logger = logging.getLogger("tts.deepgram")


class DeepgramTTS:
    URL = "https://api.deepgram.com/v1/speak"

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.voices: dict[str, str] = cfg.get("voices", {})
        self.fallback = cfg.get("fallback_tr", "aura-asteria-en")
        self.api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        self.encoding = cfg.get("encoding", "mulaw")
        self.sample_rate = int(cfg.get("sample_rate", 8000))
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
            )
        return self._client

    def _voice_for(self, lang: str) -> str:
        v = self.voices.get(lang)
        if v:
            return v
        if lang == "tr":
            return self.fallback
        return self.voices.get("en", "aura-2-orion-en")

    async def stream(self, text: str, lang: str = "de") -> AsyncIterator[bytes]:
        """HTTP-streaming synth. Yields µ-law frames (160 bytes each)."""
        if not text or not text.strip():
            return
        voice = self._voice_for(lang)
        params = {
            "model": voice,
            "encoding": self.encoding,
            "sample_rate": str(self.sample_rate),
            "container": self.cfg.get("container", "none"),
        }
        client = await self._get_client()
        buf = bytearray()
        try:
            async with client.stream(
                "POST",
                self.URL,
                params=params,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.error('"tts http %s: %s"', resp.status_code, body[:200])
                    return
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    buf.extend(chunk)
                    while len(buf) >= FRAME_BYTES:
                        yield bytes(buf[:FRAME_BYTES])
                        del buf[:FRAME_BYTES]
        except Exception as exc:
            logger.exception('"tts stream failed"')
            return
        if buf:
            frame = bytes(buf) + b"\xff" * (FRAME_BYTES - len(buf))
            yield frame

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# Turkish-specific (not shared with German): ç ğ ı ş İ
_TURKISH_ONLY = re.compile(r"[çğıİşŞĞÇ]")
# German-specific umlauts not shared with Turkish: ä ß (ö/ü exist in both)
_GERMAN_ONLY = re.compile(r"[äßÄ]")


def detect_language(text: str, default: str = "en") -> str:
    # Check Turkish-specific characters first — they outweigh shared ö/ü
    if _TURKISH_ONLY.search(text):
        return "tr"
    if _GERMAN_ONLY.search(text):
        return "de"
    if re.search(r"[öüÖÜ]", text):
        # ambiguous; default to German since ö/ü are more common in de
        return "de"
    # very light heuristic fallback based on common stopwords
    low = text.lower()
    de_hits = sum(1 for w in (" der ", " die ", " das ", " und ", " nicht ", " ist ") if w in f" {low} ")
    tr_hits = sum(1 for w in (" bir ", " için ", " değil ", " evet ", " hayır ") if w in f" {low} ")
    if de_hits >= 2:
        return "de"
    if tr_hits >= 2:
        return "tr"
    return default
