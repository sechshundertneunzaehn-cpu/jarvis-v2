"""Markdown-backed knowledge store with keyword retrieval."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

logger = logging.getLogger("knowledge")


class KnowledgeStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._seed_if_empty()
        self._docs: dict[str, str] = {}
        self._load()

    def _seed_if_empty(self) -> None:
        seeds = {
            "common.md": (
                "# Jarvis Common\n\n"
                "## Owner\n"
                "Owner: Askin (sechshundertneunzaehn@gmail.com). Primary phone: +13076670667.\n"
                "Spricht deutsch, englisch, türkisch.\n\n"
                "## House Rules\n"
                "- Keine Halluzinationen. Bei Unsicherheit: Tool-Call oder Nachfragen.\n"
                "- Während aktivem Call niemals neue Deploys.\n"
                "- Tone: direkt, kurz, professionell.\n"
            ),
            "assetsun.md": (
                "# Assetsun LLC\n\n"
                "- US-Entity registered in Wyoming.\n"
                "- Registered Agent: Wyoming EZ Corporate Filings.\n"
                "- Business activity: software/AI consulting.\n"
                "- EIN: pending (in process with IRS).\n"
                "- Primary contact: Askin (owner, sole member).\n"
                "- Bank: (tbd).\n"
            ),
            "us-ein-irs.md": (
                "# EIN / IRS Process Notes\n\n"
                "## Who to call\n"
                "IRS Business & Specialty Tax Line: +1 800-829-4933 (Mon–Fri 07:00–19:00 local).\n"
                "General IRS assistance: +1 800-829-1040.\n\n"
                "## What to say for a foreign-owner LLC\n"
                "- Request: 'I'd like to apply for an EIN for a single-member LLC.'\n"
                "- Form: SS-4; foreign owners cannot e-file, must fax/phone.\n"
                "- Responsible Party: sole member's full legal name + ITIN or 'Foreign' with passport.\n"
                "- Reason: 'Started a new business' or 'Banking purposes'.\n\n"
                "## Gotchas\n"
                "- IVR loop: press 1 (English), then 1, then 3, then 2 to reach EIN unit.\n"
                "- Hold times 30–90 min typical.\n"
                "- Agent will verbally assign EIN; write it down + request fax confirmation (Form 147C).\n"
            ),
        }
        for fname, body in seeds.items():
            p = self.root / fname
            if not p.exists():
                p.write_text(body)

    def _load(self) -> None:
        self._docs.clear()
        for p in sorted(self.root.glob("*.md")):
            self._docs[p.stem] = p.read_text()

    def count(self) -> int:
        return len(self._docs)

    def list_docs(self) -> list[str]:
        return list(self._docs.keys())

    def get(self, doc_id: str) -> Optional[str]:
        return self._docs.get(doc_id)

    def search(self, query: str, top_k: int = 3, max_chars: int = 1500) -> str:
        """Return top-k relevant passages (paragraph-granularity) joined as context."""
        if not query.strip():
            return ""
        scored: list[tuple[float, str, str]] = []
        for doc_id, body in self._docs.items():
            for para in re.split(r"\n\s*\n", body):
                p = para.strip()
                if not p:
                    continue
                score = max(
                    fuzz.partial_ratio(query.lower(), p.lower()),
                    fuzz.token_set_ratio(query.lower(), p.lower()),
                )
                if score >= 50:
                    scored.append((score, doc_id, p))
        scored.sort(reverse=True)
        out: list[str] = []
        used = 0
        for _, doc_id, p in scored[:top_k]:
            chunk = f"[{doc_id}] {p}"
            if used + len(chunk) > max_chars:
                break
            out.append(chunk)
            used += len(chunk) + 2
        return "\n\n".join(out)
