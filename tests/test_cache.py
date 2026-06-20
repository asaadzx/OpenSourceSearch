import os
import json
import tempfile
import core.cache
from core.cache import lookup_cache, save_to_cache, _get_cache_word_count


def _make_cache_file(tmp_path: str, data: list):
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def test_lookup_cache_empty_file(temp_cache_file):
    result = lookup_cache("test query")
    assert result is None


def test_lookup_cache_exact_match(temp_cache_file):
    save_to_cache({
        "original": "test query",
        "translated": "test query",
        "en_query": "test query",
        "alt_queries": [],
        "keywords": ["test"],
    })
    result = lookup_cache("test query", threshold=0.8)
    assert result is not None
    assert result.get("en_query") == "test query"


def test_lookup_cache_similar_match(temp_cache_file):
    save_to_cache({
        "original": "web scraper python",
        "translated": "web scraper python",
        "en_query": "web scraper python",
        "alt_queries": [],
        "keywords": ["web", "scraper"],
    })
    result = lookup_cache("web scraper with python", threshold=0.5)
    assert result is not None


def test_lookup_cache_no_match(temp_cache_file):
    save_to_cache({
        "original": "database tool",
        "translated": "database tool",
        "en_query": "database tool",
        "alt_queries": [],
        "keywords": [],
    })
    result = lookup_cache("web scraper python", threshold=0.8)
    assert result is None


def test_save_and_retrieve_persists(temp_cache_file):
    entry = {
        "original": "save test",
        "translated": "save test",
        "en_query": "save test",
        "alt_queries": ["alt"],
        "keywords": ["test"],
    }
    save_to_cache(entry)
    with open(temp_cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["original"] == "save test"


def test_cache_eviction(temp_cache_file):
    old_limit = core.cache.MAX_WORDS_LIMIT
    core.cache.MAX_WORDS_LIMIT = 30
    try:
        for i in range(20):
            save_to_cache({
                "original": f"query {i}",
                "translated": f"query {i}",
                "en_query": f"query {i}",
                "alt_queries": ["word1 word2 word3"],
                "keywords": ["key1 key2"],
            })
        with open(temp_cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) < 20
    finally:
        core.cache.MAX_WORDS_LIMIT = old_limit


def test_get_cache_word_count_empty():
    assert _get_cache_word_count([]) == 0


def test_get_cache_word_count_single():
    entry = {
        "original": "hello world",
        "translated": "bonjour le monde",
        "en_query": "hello",
        "alt_queries": ["hi", "hey"],
        "keywords": ["greeting"],
    }
    count = _get_cache_word_count([entry])
    assert count == 9


def test_lookup_cache_handles_corrupt_file(temp_cache_file):
    with open(temp_cache_file, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    result = lookup_cache("anything")
    assert result is None


def test_save_to_cache_handles_non_list_file(temp_cache_file):
    with open(temp_cache_file, "w", encoding="utf-8") as f:
        json.dump({"not": "a list"}, f)
    save_to_cache({
        "original": "works",
        "translated": "works",
        "en_query": "works",
        "alt_queries": [],
        "keywords": [],
    })
    with open(temp_cache_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) == 1
