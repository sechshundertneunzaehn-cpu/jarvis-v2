from tts.deepgram_tts import detect_language, DeepgramTTS


def test_detect_german_umlauts():
    assert detect_language("Schön, dass du da bist") == "de"


def test_detect_turkish():
    assert detect_language("Günaydın çocuk") == "tr"


def test_detect_default_english():
    assert detect_language("Hello there, how are you") == "en"


def test_detect_german_stopwords():
    assert detect_language("der Mann und die Frau ist da") == "de"


def test_detect_turkish_stopwords():
    # Needs two hits of the TR stopwords
    assert detect_language("bir şey için değil hayır") == "tr"


def test_voice_for_de():
    tts = DeepgramTTS(
        {"voices": {"de": "aura-2-fabian-de", "en": "aura-2-orion-en"}, "fallback_tr": "aura-asteria-en"}
    )
    assert tts._voice_for("de") == "aura-2-fabian-de"
    assert tts._voice_for("en") == "aura-2-orion-en"
    assert tts._voice_for("tr") == "aura-asteria-en"
    assert tts._voice_for("xx") == "aura-2-orion-en"
