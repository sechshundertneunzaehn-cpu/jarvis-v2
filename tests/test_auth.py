from brain.auth import is_owner_caller, passphrase_match


def test_whitelist_exact():
    assert is_owner_caller("+13076670667", ["+13076670667"])


def test_whitelist_miss():
    assert not is_owner_caller("+12125551212", ["+13076670667"])


def test_whitelist_empty():
    assert not is_owner_caller("+1", [])


def test_whitelist_none_caller():
    assert not is_owner_caller(None, ["+13076670667"])


def test_passphrase_exact():
    assert passphrase_match("Sonne über Wyoming", "Sonne über Wyoming")


def test_passphrase_fuzzy():
    # STT often drops umlauts
    assert passphrase_match("sonne ueber wyoming", "Sonne über Wyoming")


def test_passphrase_too_different():
    assert not passphrase_match("ich mag kuchen", "Sonne über Wyoming")


def test_passphrase_empty():
    assert not passphrase_match("", "Sonne über Wyoming")
