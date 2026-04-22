"""Contact registry with fuzzy-match lookup."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import yaml
from rapidfuzz import fuzz, process

logger = logging.getLogger("contacts")


class ContactRegistry:
    """YAML-backed contact store.

    Schema per entry:
        id: str (slug)
        name: str (display name)
        aliases: list[str]
        phone_e164: str
        language: str   # de|en|tr
        notes: str
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._contacts: list[dict] = []
        if self.path.exists():
            self._load()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._save_seeds()
            self._load()

    def _load(self) -> None:
        with self._lock:
            data = yaml.safe_load(self.path.read_text()) or {}
            self._contacts = data.get("contacts", [])

    def _save(self) -> None:
        with self._lock:
            self.path.write_text(
                yaml.safe_dump({"contacts": self._contacts}, sort_keys=False, allow_unicode=True)
            )

    def _save_seeds(self) -> None:
        seeds = {
            "contacts": [
                {
                    "id": "irs",
                    "name": "IRS (US Internal Revenue Service)",
                    "aliases": ["IRS", "Finanzamt USA", "Tax Office", "Steuerbehoerde"],
                    "phone_e164": "+18008291040",
                    "language": "en",
                    "notes": "EIN/ITIN business line; expect long IVR",
                },
                {
                    "id": "wyoming_ez_corp",
                    "name": "Wyoming EZ Corporate Filings",
                    "aliases": ["Wyoming EZ", "EZ Corp", "Wyoming Registered Agent"],
                    "phone_e164": "+13073442554",
                    "language": "en",
                    "notes": "Askin's LLC registered agent",
                },
                {
                    "id": "mutter",
                    "name": "Mutter",
                    "aliases": ["Mama", "Mutti", "Mom"],
                    "phone_e164": "+4917000000000",
                    "language": "de",
                    "notes": "placeholder, update via add_contact",
                },
                {
                    "id": "askin_laptop",
                    "name": "Askin (Laptop)",
                    "aliases": ["Askin", "Boss", "Chef"],
                    "phone_e164": "+13076670667",
                    "language": "tr",
                    "notes": "owner's Twilio voice-webhook number",
                },
                {
                    "id": "testcall",
                    "name": "Testcall",
                    "aliases": ["testcall", "test call", "test nummer", "testnummer"],
                    "phone_e164": "+18042221111",
                    "language": "en",
                    "notes": "test endpoint for dial-flow verification",
                    "owner_accessible": True,
                },
            ]
        }
        self.path.write_text(yaml.safe_dump(seeds, sort_keys=False, allow_unicode=True))

    def count(self) -> int:
        with self._lock:
            return len(self._contacts)

    def all(self) -> list[dict]:
        with self._lock:
            return list(self._contacts)

    def by_id(self, cid: str) -> Optional[dict]:
        with self._lock:
            for c in self._contacts:
                if c["id"] == cid:
                    return c
            return None

    def find(self, query: str, threshold: int = 80) -> Optional[dict]:
        """Fuzzy-match by name + aliases. Returns best match above threshold."""
        with self._lock:
            if not query or not self._contacts:
                return None
            candidates: list[tuple[str, int]] = []  # (haystack, index)
            for idx, c in enumerate(self._contacts):
                candidates.append((c["name"], idx))
                for a in c.get("aliases", []):
                    candidates.append((a, idx))
            hay = [c[0] for c in candidates]
            match = process.extractOne(
                query, hay, scorer=fuzz.WRatio, score_cutoff=threshold
            )
            if not match:
                return None
            _, score, pos = match
            return self._contacts[candidates[pos][1]]

    def add(self, entry: dict) -> dict:
        required = {"id", "name", "phone_e164"}
        if missing := required - entry.keys():
            raise ValueError(f"missing fields: {missing}")
        entry.setdefault("aliases", [])
        entry.setdefault("language", "de")
        entry.setdefault("notes", "")
        with self._lock:
            for c in self._contacts:
                if c["id"] == entry["id"]:
                    raise ValueError(f"duplicate id: {entry['id']}")
            self._contacts.append(entry)
            self._save()
        return entry
