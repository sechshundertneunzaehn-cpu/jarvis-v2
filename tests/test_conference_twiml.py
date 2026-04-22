"""Twilio bridge TwiML tests (no network) — Connect-Stream direct design."""
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    class FakeCalls:
        def __init__(self):
            self.created: list[dict] = []

        def create(self, **kw):
            self.created.append(kw)
            return SimpleNamespace(sid=f"CA_fake_{len(self.created)}")

        def __call__(self, sid):
            return SimpleNamespace(update=lambda **kw: None)

    class FakeClient:
        def __init__(self, *a, **kw):
            self.calls = FakeCalls()

    monkeypatch.setattr("bridge.twilio_conf.TwilioClient", FakeClient)

    os.environ.setdefault("TWILIO_ACCOUNT_SID", "AC_test")
    os.environ.setdefault("TWILIO_AUTH_TOKEN", "test")
    os.environ.setdefault("TWILIO_NUMBER", "+15005550006")

    from app import app

    with TestClient(app) as c:
        yield c


def test_inbound_returns_connect_stream(client):
    r = client.post(
        "/v2/twilio/voice-inbound",
        data={"From": "+13076670667", "To": "+1", "CallSid": "CA_owner"},
    )
    assert r.status_code == 200
    body = r.text
    assert "<Connect>" in body
    assert "<Stream" in body
    assert "stream/" in body
    assert "/user" in body
    # No Conference in the direct-stream design
    assert "<Conference" not in body


def test_inbound_sets_owner_from_whitelist(client):
    r = client.post(
        "/v2/twilio/voice-inbound",
        data={"From": "+13076670667", "To": "+1", "CallSid": "CA_owner2"},
    )
    assert r.status_code == 200
    from app import app

    sess = list(app.state.sessions._by_pair.values())[-1]
    assert sess.is_owner is True
    assert sess.authed is True


def test_inbound_non_owner_not_authed(client):
    r = client.post(
        "/v2/twilio/voice-inbound",
        data={"From": "+19999999999", "To": "+1", "CallSid": "CA_stranger"},
    )
    assert r.status_code == 200
    from app import app

    sess = list(app.state.sessions._by_pair.values())[-1]
    assert sess.is_owner is False
    assert sess.authed is False


def test_voice_target_join_unknown_pair_hangups(client):
    r = client.post(
        "/v2/twilio/voice-target-join?pair_id=doesnotexist",
        data={"CallSid": "CA_x"},
    )
    assert "<Hangup" in r.text


def test_voice_target_join_returns_stream(client):
    # Create a session via inbound
    client.post(
        "/v2/twilio/voice-inbound",
        data={"From": "+13076670667", "To": "+1", "CallSid": "CA_a"},
    )
    from app import app

    pair = list(app.state.sessions._by_pair.values())[-1].pair_id
    r = client.post(
        f"/v2/twilio/voice-target-join?pair_id={pair}",
        data={"CallSid": "CA_target"},
    )
    assert r.status_code == 200
    assert "<Connect>" in r.text
    assert "/target" in r.text


def test_outbound_dial_unknown_pair_404(client):
    r = client.post(
        "/v2/twilio/outbound-dial",
        data={"pair_id": "missing", "target_e164": "+18005551212"},
    )
    assert r.status_code == 404


def test_outbound_dial_happy_path(client):
    client.post(
        "/v2/twilio/voice-inbound",
        data={"From": "+13076670667", "To": "+1", "CallSid": "CA_in"},
    )
    from app import app

    pair = list(app.state.sessions._by_pair.values())[-1].pair_id
    r = client.post(
        "/v2/twilio/outbound-dial",
        data={"pair_id": pair, "target_e164": "+18005551212"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["call_sid"].startswith("CA_fake_")


def test_health_endpoint(client):
    r = client.get("/v2/health")
    assert r.status_code == 200
    j = r.json()
    assert j["service"] == "jarvis-v2"
    assert j["models"]["brain"].startswith("claude-sonnet-")
    # Lite-build observability fields
    assert j["stt_lang"] == "de"
    assert j["stt_allowed_langs"] == ["de"]
    assert j["barge_in_enabled"] is False
    assert j["stt_post_hold_ms"] == 0
    assert "contacts_loaded_names" in j
    assert isinstance(j["tts_voices"], dict)


def test_ping(client):
    r = client.get("/v2/ping")
    assert r.status_code == 200
    assert r.text == "pong"


def test_active_calls(client):
    r = client.get("/v2/active-calls")
    assert r.status_code == 200
    assert "active_count" in r.json()


def test_legacy_bot_join_hangups(client):
    r = client.post("/v2/twilio/voice-bot-join", data={})
    assert "<Hangup" in r.text


def test_call_status_200(client):
    r = client.post(
        "/v2/twilio/call-status",
        data={"CallStatus": "completed", "CallSid": "CAx"},
    )
    assert r.status_code == 200
