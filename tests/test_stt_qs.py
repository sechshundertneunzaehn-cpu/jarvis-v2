from stt.deepgram_ws import DeepgramSTT


def _cfg():
    return {
        "model": "nova-3",
        "language": "multi",
        "encoding": "mulaw",
        "sample_rate": 8000,
        "interim_results": True,
        "utterance_end_ms": 1000,
        "endpointing": 300,
        "vad_events": True,
        "smart_format": True,
    }


def test_qs_contains_all_params():
    stt = DeepgramSTT(_cfg())
    qs = stt._qs()
    for part in (
        "model=nova-3",
        "language=multi",
        "encoding=mulaw",
        "sample_rate=8000",
        "interim_results=true",
        "utterance_end_ms=1000",
        "endpointing=300",
        "vad_events=true",
        "smart_format=true",
    ):
        assert part in qs, f"missing {part} in {qs}"


def test_qs_booleans_false():
    cfg = _cfg()
    cfg["interim_results"] = False
    cfg["vad_events"] = False
    stt = DeepgramSTT(cfg)
    qs = stt._qs()
    assert "interim_results=false" in qs
    assert "vad_events=false" in qs
