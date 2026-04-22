"""Per-session cost tracker with soft-hangup on cap."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("brain.cost")


@dataclass
class CostMeter:
    rates: dict
    cap_usd: float = 5.0
    warn_ratio: float = 0.75
    hangup_ratio: float = 1.0
    twilio_call_minutes: float = 0.0
    twilio_conf_minutes: float = 0.0
    deepgram_stt_minutes: float = 0.0
    deepgram_tts_chars: int = 0
    claude_input_tokens: int = 0
    claude_output_tokens: int = 0
    _warned: bool = False
    _hung: bool = False

    def add_stt_seconds(self, sec: float) -> None:
        self.deepgram_stt_minutes += sec / 60.0

    def add_tts_chars(self, chars: int) -> None:
        self.deepgram_tts_chars += chars

    def add_call_seconds(self, sec: float, legs: int = 2) -> None:
        self.twilio_call_minutes += sec / 60.0 * legs
        self.twilio_conf_minutes += sec / 60.0

    def add_claude(self, input_tok: int, output_tok: int) -> None:
        self.claude_input_tokens += input_tok
        self.claude_output_tokens += output_tok

    def total_usd(self) -> float:
        r = self.rates
        return (
            self.twilio_call_minutes * r["twilio_voice_per_min"]
            + self.twilio_conf_minutes * r["twilio_conf_per_min"]
            + self.deepgram_stt_minutes * r["deepgram_stt_per_min"]
            + (self.deepgram_tts_chars / 1000.0) * r["deepgram_tts_per_1k_chars"]
            + (self.claude_input_tokens / 1_000_000.0) * r["claude_input_per_mtok"]
            + (self.claude_output_tokens / 1_000_000.0) * r["claude_output_per_mtok"]
        )

    def breakdown(self) -> dict:
        r = self.rates
        return {
            "twilio_voice": round(self.twilio_call_minutes * r["twilio_voice_per_min"], 4),
            "twilio_conf": round(self.twilio_conf_minutes * r["twilio_conf_per_min"], 4),
            "deepgram_stt": round(self.deepgram_stt_minutes * r["deepgram_stt_per_min"], 4),
            "deepgram_tts": round((self.deepgram_tts_chars / 1000.0) * r["deepgram_tts_per_1k_chars"], 4),
            "claude_in": round((self.claude_input_tokens / 1_000_000.0) * r["claude_input_per_mtok"], 4),
            "claude_out": round((self.claude_output_tokens / 1_000_000.0) * r["claude_output_per_mtok"], 4),
            "total": round(self.total_usd(), 4),
            "cap": self.cap_usd,
        }

    def should_warn(self) -> bool:
        if self._warned:
            return False
        if self.total_usd() >= self.cap_usd * self.warn_ratio:
            self._warned = True
            return True
        return False

    def should_hangup(self) -> bool:
        if self._hung:
            return False
        if self.total_usd() >= self.cap_usd * self.hangup_ratio:
            self._hung = True
            return True
        return False
