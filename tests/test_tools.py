import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from bridge.session import Session
from brain.tools import dispatch, TOOL_SCHEMAS
from contacts.registry import ContactRegistry
from knowledge.store import KnowledgeStore


@pytest.fixture
def sess():
    return Session()


@pytest.fixture
def app_state(tmp_path: Path):
    return SimpleNamespace(
        contacts=ContactRegistry(tmp_path / "c.yaml"),
        knowledge=KnowledgeStore(tmp_path / "kb"),
        config={"service": {"base_url": "http://127.0.0.1:18793", "path_prefix": "/v2"}},
    )


def test_tool_schemas_present():
    names = {t["name"] for t in TOOL_SCHEMAS}
    required = {
        "dial_contact",
        "hangup",
        "set_mode",
        "get_knowledge",
        "list_contacts",
        "add_contact",
        "save_note",
        "get_current_time",
    }
    assert required <= names


@pytest.mark.asyncio
async def test_set_mode_ok(sess, app_state):
    r = await dispatch("set_mode", {"mode": "interpreter"}, sess=sess, app_state=app_state)
    assert r["ok"] and sess.mode.value == "interpreter"


@pytest.mark.asyncio
async def test_set_mode_invalid(sess, app_state):
    r = await dispatch("set_mode", {"mode": "debug"}, sess=sess, app_state=app_state)
    assert not r["ok"]


@pytest.mark.asyncio
async def test_list_contacts(sess, app_state):
    r = await dispatch("list_contacts", {}, sess=sess, app_state=app_state)
    assert r["ok"] and len(r["contacts"]) >= 4


@pytest.mark.asyncio
async def test_add_contact(sess, app_state):
    r = await dispatch(
        "add_contact",
        {"id": "new1", "name": "New One", "phone_e164": "+15557770000"},
        sess=sess,
        app_state=app_state,
    )
    assert r["ok"]
    assert app_state.contacts.by_id("new1")


@pytest.mark.asyncio
async def test_save_note(sess, app_state):
    r = await dispatch("save_note", {"text": "Rückruf morgen"}, sess=sess, app_state=app_state)
    assert r["ok"] and r["note_count"] == 1


@pytest.mark.asyncio
async def test_save_note_empty(sess, app_state):
    r = await dispatch("save_note", {"text": "   "}, sess=sess, app_state=app_state)
    assert not r["ok"]


@pytest.mark.asyncio
async def test_get_current_time_default(sess, app_state):
    r = await dispatch("get_current_time", {}, sess=sess, app_state=app_state)
    assert r["ok"]
    assert "T" in r["iso"]
    assert r["timezone"] == "Europe/Berlin"


@pytest.mark.asyncio
async def test_get_current_time_invalid_tz(sess, app_state):
    r = await dispatch(
        "get_current_time", {"timezone": "Mars/Olympus"}, sess=sess, app_state=app_state
    )
    assert not r["ok"]


@pytest.mark.asyncio
async def test_get_knowledge(sess, app_state):
    r = await dispatch(
        "get_knowledge", {"query": "IRS EIN"}, sess=sess, app_state=app_state
    )
    assert r["ok"]
    assert "us-ein-irs" in r["docs"]


@pytest.mark.asyncio
async def test_unknown_tool(sess, app_state):
    r = await dispatch("no_such_tool", {}, sess=sess, app_state=app_state)
    assert not r["ok"]


@pytest.mark.asyncio
async def test_dial_contact_unknown_name(sess, app_state):
    r = await dispatch(
        "dial_contact", {"query": "zzzz-unknown"}, sess=sess, app_state=app_state
    )
    assert not r["ok"]


@pytest.mark.asyncio
async def test_dial_contact_matches_mama(sess, app_state, monkeypatch):
    calls = {}

    class FakeResp:
        status_code = 200
        text = '{"ok":true}'

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data):
            calls["url"] = url
            calls["data"] = dict(data)
            return FakeResp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    r = await dispatch("dial_contact", {"query": "Mama"}, sess=sess, app_state=app_state)
    assert r["ok"]
    assert r["dialed"] == "Mutter"
    assert calls["data"]["pair_id"] == sess.pair_id


@pytest.mark.asyncio
async def test_dial_contact_e164(sess, app_state, monkeypatch):
    class FakeResp:
        status_code = 200

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data):
            return FakeResp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    r = await dispatch(
        "dial_contact", {"query": "+18005551234"}, sess=sess, app_state=app_state
    )
    assert r["ok"]
    assert r["phone_e164"] == "+18005551234"
