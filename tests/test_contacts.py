from pathlib import Path

import pytest

from contacts.registry import ContactRegistry


@pytest.fixture
def tmp_registry(tmp_path: Path) -> ContactRegistry:
    return ContactRegistry(tmp_path / "contacts.yaml")


def test_seed_contacts_loaded(tmp_registry: ContactRegistry):
    ids = {c["id"] for c in tmp_registry.all()}
    assert {"irs", "wyoming_ez_corp", "mutter", "askin_laptop"} <= ids
    assert tmp_registry.count() >= 4


def test_find_exact_name(tmp_registry: ContactRegistry):
    c = tmp_registry.find("IRS")
    assert c and c["id"] == "irs"


def test_find_fuzzy_alias(tmp_registry: ContactRegistry):
    c = tmp_registry.find("Tax Office")
    assert c and c["id"] == "irs"


def test_find_fuzzy_typo(tmp_registry: ContactRegistry):
    c = tmp_registry.find("Wyoming EZ Coprorate")
    assert c and c["id"] == "wyoming_ez_corp"


def test_find_mama(tmp_registry: ContactRegistry):
    c = tmp_registry.find("Mama")
    assert c and c["id"] == "mutter"


def test_find_below_threshold(tmp_registry: ContactRegistry):
    assert tmp_registry.find("xyzabc_totally_unrelated") is None


def test_add_contact_valid(tmp_registry: ContactRegistry):
    entry = tmp_registry.add(
        {"id": "test1", "name": "Test One", "phone_e164": "+15551112222"}
    )
    assert entry["aliases"] == []
    assert tmp_registry.by_id("test1")["name"] == "Test One"


def test_add_contact_duplicate(tmp_registry: ContactRegistry):
    tmp_registry.add({"id": "dup", "name": "x", "phone_e164": "+1"})
    with pytest.raises(ValueError):
        tmp_registry.add({"id": "dup", "name": "y", "phone_e164": "+2"})


def test_add_contact_missing_fields(tmp_registry: ContactRegistry):
    with pytest.raises(ValueError):
        tmp_registry.add({"id": "x"})


def test_persistence_across_instances(tmp_path: Path):
    r1 = ContactRegistry(tmp_path / "c.yaml")
    r1.add({"id": "p1", "name": "P1", "phone_e164": "+19000000000"})
    r2 = ContactRegistry(tmp_path / "c.yaml")
    assert r2.by_id("p1")["phone_e164"] == "+19000000000"


def test_find_empty_string(tmp_registry: ContactRegistry):
    assert tmp_registry.find("") is None
