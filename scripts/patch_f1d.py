"""Patch brain/tools.py for F1D hangup guard."""
from __future__ import annotations

PATH = "/opt/jarvis-v2/brain/tools.py"

HELPER = r"""
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


"""

ANCHOR = "async def dispatch(tool_name: str, args: dict, *, sess, app_state) -> dict:"

OLD_HEAD = (
    "async def _hangup(args: dict, sess, app_state) -> dict:\n"
    "    target = args.get(\"target\", \"all\")\n"
    "    from twilio.rest import Client as TwilioClient"
)

NEW_HEAD = (
    "async def _hangup(args: dict, sess, app_state) -> dict:\n"
    "    target = args.get(\"target\", \"all\")\n"
    "    if not _user_asked_for_hangup(sess):\n"
    "        logger.info(json.dumps({\n"
    "            \"event\": \"hangup_trigger\",\n"
    "            \"pair_id\": getattr(sess, \"pair_id\", None),\n"
    "            \"reason\": \"blocked_no_explicit_user_command\",\n"
    "            \"target\": target,\n"
    "            \"last_user_text\": _last_user_text(sess)[-200:],\n"
    "        }))\n"
    "        return {\n"
    "            \"ok\": False,\n"
    "            \"error\": \"hangup blocked: user did not explicitly ask to hang up. Only call hangup when the user says leg auf/auflegen/hang up/end call or clear equivalent.\",\n"
    "        }\n"
    "    logger.info(json.dumps({\n"
    "        \"event\": \"hangup_trigger\",\n"
    "        \"pair_id\": getattr(sess, \"pair_id\", None),\n"
    "        \"reason\": \"explicit_user_command\",\n"
    "        \"target\": target,\n"
    "    }))\n"
    "    from twilio.rest import Client as TwilioClient"
)

OLD_SCHEMA = (
    "        \"name\": \"hangup\",\n"
    "        \"description\": \"End the call, or selectively drop one leg.\","
)

NEW_SCHEMA = (
    "        \"name\": \"hangup\",\n"
    "        \"description\": (\n"
    "            \"End the call, or selectively drop one leg. DO NOT call this tool unless the user has \"\n"
    "            \"explicitly said leg auf / auflegen / beende den Anruf / hang up / end call \"\n"
    "            \"or a clear equivalent in the most recent turn. Never call it on silence, pauses, \"\n"
    "            \"mode-switches, or because the conversation seems finished.\"\n"
    "        ),"
)


def main() -> None:
    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    if "HANGUP_PHRASES" not in src:
        assert ANCHOR in src, "dispatch anchor not found"
        src = src.replace(ANCHOR, HELPER + ANCHOR, 1)

    assert OLD_HEAD in src, "_hangup head not found"
    src = src.replace(OLD_HEAD, NEW_HEAD, 1)

    assert OLD_SCHEMA in src, "hangup schema not found"
    src = src.replace(OLD_SCHEMA, NEW_SCHEMA, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("tools.py patched OK")


if __name__ == "__main__":
    main()
