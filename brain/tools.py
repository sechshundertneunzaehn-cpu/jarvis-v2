"""Tool-definitions + dispatcher for the Claude agent."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger("brain.tools")


TOOL_SCHEMAS: list[dict] = [
    {
        "name": "dial_contact",
        "description": (
            "Dial a contact by fuzzy name, alias (e.g. 'Testcall', 'IRS', 'Mutter'), "
            "or explicit E.164 number. Bridges the called party into the live call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name/alias from the contact registry, OR an E.164 phone number.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "hangup",
        "description": (
            "End the call, or selectively drop one leg. DO NOT call this tool unless the user has "
            "explicitly said leg auf / auflegen / beende den Anruf / hang up / end call "
            "or a clear equivalent in the most recent turn. Never call it on silence, pauses, "
            "mode-switches, or because the conversation seems finished."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "enum": ["all", "user", "target", "bot"],
                    "description": "Which leg(s) to drop. Default 'all' ends the whole session.",
                }
            },
        },
    },
    {
        "name": "set_mode",
        "description": "Switch between assistant and interpreter modes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["assistant", "interpreter"]},
            },
            "required": ["mode"],
        },
    },
    {
        "name": "get_knowledge",
        "description": "Retrieve relevant passages from the knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_contacts",
        "description": "List all contacts in the directory.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_contact",
        "description": "Create a new contact entry.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "phone_e164": {"type": "string"},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "language": {"type": "string", "enum": ["de", "en", "tr"]},
                "notes": {"type": "string"},
            },
            "required": ["id", "name", "phone_e164"],
        },
    },
    {
        "name": "save_note",
        "description": "Append a note to the current call session.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "get_current_time",
        "description": "Return the current time in a given timezone (IANA name).",
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "default": "Europe/Berlin",
                }
            },
        },
    },
]



HANGUP_PHRASES: tuple[str, ...] = (
    "leg auf",
    "legst auf",
    "auflegen",
    "leg den anruf auf",
    "beende den anruf",
    "beende das gespräch",
    "beende das gespraech",
    "beenden wir",
    "hang up",
    "hangup",
    "end call",
    "end the call",
    "drop the call",
    "kapat",
    "telefonu kapat",
)


def _last_user_text(sess, lookback: int = 6) -> str:
    texts: list[str] = []
    for m in reversed(sess.history or []):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            texts.append(content)
            if len(texts) >= lookback:
                break
    return "\n".join(reversed(texts)).lower()


def _user_asked_for_hangup(sess) -> bool:
    tail = _last_user_text(sess)
    return any(p in tail for p in HANGUP_PHRASES)


async def dispatch(tool_name: str, args: dict, *, sess, app_state) -> dict:
    try:
        if tool_name == "dial_contact":
            return await _dial_contact(args, sess, app_state)
        if tool_name == "hangup":
            return await _hangup(args, sess, app_state)
        if tool_name == "set_mode":
            return _set_mode(args, sess)
        if tool_name == "get_knowledge":
            return _get_knowledge(args, app_state)
        if tool_name == "list_contacts":
            return _list_contacts(app_state)
        if tool_name == "add_contact":
            return _add_contact(args, app_state)
        if tool_name == "save_note":
            return _save_note(args, sess)
        if tool_name == "get_current_time":
            return _get_current_time(args)
        return {"ok": False, "error": f"unknown tool {tool_name}"}
    except Exception as exc:
        logger.exception('"tool dispatch failed"')
        return {"ok": False, "error": str(exc)}


def _is_e164(s: str) -> bool:
    return s.startswith("+") and s[1:].isdigit() and 7 <= len(s) <= 16


async def _dial_contact(args: dict, sess, app_state) -> dict:
    query = args.get("query", "").strip()
    if not query:
        logger.info(json.dumps({"event": "dial_contact", "pair_id": sess.pair_id, "query": "", "match": None, "error": "empty"}))
        return {"ok": False, "error": "empty query"}
    if _is_e164(query):
        target = query
        display = query
        logger.info(json.dumps({"event": "dial_contact", "pair_id": sess.pair_id, "query": query, "match": "e164", "phone": target}))
    else:
        contact = app_state.contacts.find(query)
        if not contact:
            logger.info(json.dumps({"event": "dial_contact", "pair_id": sess.pair_id, "query": query, "match": None}))
            return {"ok": False, "error": f"no contact matched '{query}'"}
        target = contact["phone_e164"]
        display = contact["name"]
        logger.info(json.dumps({"event": "dial_contact", "pair_id": sess.pair_id, "query": query, "match": contact.get("id"), "phone": target}))

    cfg = app_state.config["service"]
    base = cfg["base_url"].rstrip("/") + cfg["path_prefix"]
    url = f"{base}/twilio/outbound-dial"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url, data={"pair_id": sess.pair_id, "target_e164": target}
            )
        if resp.status_code >= 300:
            return {"ok": False, "error": f"dial HTTP {resp.status_code}", "body": resp.text[:200]}
        return {"ok": True, "dialed": display, "phone_e164": target}
    except Exception as exc:
        return {"ok": False, "error": f"dial failed: {exc}"}


async def _hangup(args: dict, sess, app_state) -> dict:
    target = args.get("target", "all")
    if not _user_asked_for_hangup(sess):
        logger.info(json.dumps({
            "event": "hangup_trigger",
            "pair_id": getattr(sess, "pair_id", None),
            "reason": "blocked_no_explicit_user_command",
            "target": target,
            "last_user_text": _last_user_text(sess)[-200:],
        }))
        return {
            "ok": False,
            "error": "hangup blocked: user did not explicitly ask to hang up. Only call hangup when the user says leg auf/auflegen/hang up/end call or clear equivalent.",
        }
    logger.info(json.dumps({
        "event": "hangup_trigger",
        "pair_id": getattr(sess, "pair_id", None),
        "reason": "explicit_user_command",
        "target": target,
    }))
    from twilio.rest import Client as TwilioClient

    client = TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    dropped: list[str] = []
    if target == "all":
        for role, leg in list(sess.legs.items()):
            if leg.call_sid and not leg.hung_up_at:
                try:
                    client.calls(leg.call_sid).update(status="completed")
                    sess.mark_leg_left(role)
                    dropped.append(role)
                except Exception as exc:
                    logger.warning('"hangup leg %s failed: %s"', role, exc)
        sess.end()
    else:
        leg = sess.legs.get(target)
        if not leg or not leg.call_sid:
            return {"ok": False, "error": f"no leg '{target}'"}
        try:
            client.calls(leg.call_sid).update(status="completed")
            sess.mark_leg_left(target)
            dropped.append(target)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": True, "dropped": dropped}


def _set_mode(args: dict, sess) -> dict:
    from bridge.session import Mode

    mode = args.get("mode")
    if mode not in ("assistant", "interpreter"):
        return {"ok": False, "error": "mode must be assistant|interpreter"}
    sess.mode = Mode(mode)
    return {"ok": True, "mode": mode}


def _get_knowledge(args: dict, app_state) -> dict:
    q = args.get("query", "")
    top_k = int(args.get("top_k", 3))
    passages = app_state.knowledge.search(q, top_k=top_k)
    return {"ok": True, "passages": passages, "docs": app_state.knowledge.list_docs()}


def _list_contacts(app_state) -> dict:
    items = [
        {k: c[k] for k in ("id", "name", "phone_e164", "language") if k in c}
        for c in app_state.contacts.all()
    ]
    return {"ok": True, "contacts": items}


def _add_contact(args: dict, app_state) -> dict:
    try:
        entry = app_state.contacts.add(args)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "contact": entry}


def _save_note(args: dict, sess) -> dict:
    text = args.get("text", "").strip()
    if not text:
        return {"ok": False, "error": "empty"}
    sess.notes.append({"ts": datetime.now(timezone.utc).isoformat(), "text": text})
    return {"ok": True, "note_count": len(sess.notes)}


def _get_current_time(args: dict) -> dict:
    tz_name = args.get("timezone") or "Europe/Berlin"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        return {"ok": False, "error": f"unknown timezone {tz_name}"}
    now = datetime.now(tz)
    return {"ok": True, "timezone": tz_name, "iso": now.isoformat(), "human": now.strftime("%A, %d.%m.%Y %H:%M %Z")}
