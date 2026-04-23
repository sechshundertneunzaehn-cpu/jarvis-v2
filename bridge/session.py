"""Session + phase-machine for a single call/pair."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(str, Enum):
    INIT = "init"
    RINGING = "ringing"
    GREETING = "greeting"
    AUTHED = "authed"
    INTERPRETER = "interpreter"
    ASSISTANT = "assistant"
    DIALING = "dialing"
    BRIDGED = "bridged"
    ENDED = "ended"


class Mode(str, Enum):
    INTERPRETER = "interpreter"
    ASSISTANT = "assistant"


@dataclass
class Leg:
    role: str
    call_sid: Optional[str] = None
    joined_at: Optional[float] = None
    hung_up_at: Optional[float] = None


@dataclass
class Session:
    pair_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    phase: Phase = Phase.INIT
    mode: Mode = Mode.ASSISTANT
    caller_id: Optional[str] = None
    is_owner: bool = False
    authed: bool = False
    conference_sid: Optional[str] = None
    conference_name: Optional[str] = None
    legs: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    cost_usd: float = 0.0
    last_language: str = "de"
    tts_active: bool = False
    cost_meter: object = None  # CostMeter injected at session creation
    # F1A: second STT instance for target-leg when in interpreter mode.
    user_lang: str = "de"
    target_lang: str = "en"
    stt_target: object = None
    stt_target_task: object = None

    def add_leg(self, role: str, call_sid: Optional[str] = None) -> Leg:
        leg = Leg(role=role, call_sid=call_sid, joined_at=time.time())
        self.legs[role] = leg
        return leg

    def mark_leg_left(self, role: str) -> None:
        leg = self.legs.get(role)
        if leg:
            leg.hung_up_at = time.time()

    def duration_s(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    def end(self) -> None:
        self.phase = Phase.ENDED
        self.ended_at = time.time()

    def snapshot(self) -> dict:
        cost = round(self.cost_meter.total_usd(), 4) if self.cost_meter else round(self.cost_usd, 4)
        cost_bd = self.cost_meter.breakdown() if self.cost_meter else None
        return {
            "pair_id": self.pair_id,
            "phase": self.phase.value,
            "mode": self.mode.value,
            "caller_id": self.caller_id,
            "is_owner": self.is_owner,
            "authed": self.authed,
            "conference_name": self.conference_name,
            "legs": {
                r: {"call_sid": l.call_sid, "joined_at": l.joined_at, "hung_up_at": l.hung_up_at}
                for r, l in self.legs.items()
            },
            "duration_s": round(self.duration_s(), 1),
            "cost_usd": cost,
            "cost_breakdown": cost_bd,
            "note_count": len(self.notes),
            "history_turns": len(self.history),
        }


class SessionStore:
    """Thread-safe in-memory session map indexed by pair_id and call_sid."""

    def __init__(self) -> None:
        self._by_pair: dict[str, Session] = {}
        self._call_to_pair: dict[str, str] = {}
        self._lock = threading.RLock()

    def new(self, caller_id: Optional[str] = None, cost_meter: object = None) -> Session:
        s = Session(caller_id=caller_id, phase=Phase.RINGING, cost_meter=cost_meter)
        s.conference_name = f"pair-{s.pair_id}"
        with self._lock:
            self._by_pair[s.pair_id] = s
        return s

    def get(self, pair_id: str) -> Optional[Session]:
        with self._lock:
            return self._by_pair.get(pair_id)

    def bind_call(self, pair_id: str, call_sid: str) -> None:
        with self._lock:
            self._call_to_pair[call_sid] = pair_id

    def by_call(self, call_sid: str) -> Optional[Session]:
        with self._lock:
            pid = self._call_to_pair.get(call_sid)
            return self._by_pair.get(pid) if pid else None

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._by_pair.values() if s.phase != Phase.ENDED)

    def dashboard(self) -> dict:
        with self._lock:
            return {
                "active_count": self.active_count(),
                "sessions": [s.snapshot() for s in self._by_pair.values() if s.phase != Phase.ENDED],
            }

    def purge_ended(self, older_than_s: float = 3600) -> int:
        cutoff = time.time() - older_than_s
        removed = 0
        with self._lock:
            for pid in list(self._by_pair):
                s = self._by_pair[pid]
                if s.phase == Phase.ENDED and (s.ended_at or 0) < cutoff:
                    for leg in s.legs.values():
                        if leg.call_sid:
                            self._call_to_pair.pop(leg.call_sid, None)
                    del self._by_pair[pid]
                    removed += 1
        return removed
