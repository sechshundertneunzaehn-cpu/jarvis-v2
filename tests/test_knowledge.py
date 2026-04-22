from pathlib import Path

import pytest

from knowledge.store import KnowledgeStore


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path)


def test_seed_docs(store: KnowledgeStore):
    assert store.count() >= 3
    docs = set(store.list_docs())
    assert {"common", "assetsun", "us-ein-irs"} <= docs


def test_get_doc(store: KnowledgeStore):
    assert "Jarvis" in store.get("common")
    assert store.get("missing") is None


def test_search_ein(store: KnowledgeStore):
    res = store.search("EIN application IRS")
    assert "IRS" in res or "EIN" in res
    assert "[us-ein-irs]" in res


def test_search_assetsun(store: KnowledgeStore):
    res = store.search("Wyoming LLC registered agent")
    assert "[assetsun]" in res or "[us-ein-irs]" in res


def test_search_empty_query(store: KnowledgeStore):
    assert store.search("") == ""


def test_search_no_match_gets_truncated(store: KnowledgeStore):
    res = store.search("quantum chromodynamics")
    assert res == "" or len(res) < 1500
