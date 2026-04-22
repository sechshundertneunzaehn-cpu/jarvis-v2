import pytest

from brain.cost import CostMeter


RATES = {
    "twilio_voice_per_min": 0.01,
    "twilio_conf_per_min": 0.002,
    "deepgram_stt_per_min": 0.0077,
    "deepgram_tts_per_1k_chars": 0.030,
    "claude_input_per_mtok": 3.0,
    "claude_output_per_mtok": 15.0,
}


def _meter(**kw):
    return CostMeter(rates=RATES, cap_usd=5.0, warn_ratio=0.75, hangup_ratio=1.0, **kw)


def test_zero_baseline():
    m = _meter()
    assert m.total_usd() == 0.0
    assert not m.should_warn()
    assert not m.should_hangup()


def test_stt_accounting():
    m = _meter()
    m.add_stt_seconds(60)
    assert round(m.total_usd(), 4) == 0.0077


def test_tts_accounting():
    m = _meter()
    m.add_tts_chars(2000)
    assert round(m.total_usd(), 4) == round(2 * 0.030, 4)


def test_claude_tokens():
    m = _meter()
    m.add_claude(1_000_000, 500_000)
    expected = 3.0 + 0.5 * 15.0
    assert round(m.total_usd(), 4) == round(expected, 4)


def test_call_seconds_two_legs():
    m = _meter()
    m.add_call_seconds(60, legs=2)
    assert round(m.total_usd(), 4) == round(2 * 0.01 + 0.002, 4)


def test_warn_fires_once():
    m = _meter()
    # Force $4 (80% of $5 cap)
    m.add_claude(0, int(4 / 15.0 * 1_000_000))
    assert m.should_warn()
    assert not m.should_warn()  # latched


def test_hangup_fires_once():
    m = _meter()
    m.add_claude(0, int(6 / 15.0 * 1_000_000))
    assert m.should_hangup()
    assert not m.should_hangup()


def test_breakdown_shape():
    m = _meter()
    m.add_stt_seconds(30)
    m.add_tts_chars(500)
    b = m.breakdown()
    for k in ("twilio_voice", "twilio_conf", "deepgram_stt", "deepgram_tts", "claude_in", "claude_out", "total", "cap"):
        assert k in b
    assert b["cap"] == 5.0
