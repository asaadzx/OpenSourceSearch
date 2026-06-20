from utils.translation import detect_language
from search_engines.platform_base import prefilter_results, smart_deduplicate, search_ddg
from search_engines.github_search import fetch_repo_info
from search_engines.platform_base import prefilter_results
from ai_backend.llm_handler import safe_parse_ai_json


def test_prefilter_basic():
    results = [
        {"title": "python scraper", "body": "scrape websites with python"},
        {"title": "css framework", "body": "utility-first css"},
    ]
    filtered = prefilter_results(results, ["scrape"])
    assert len(filtered) >= 1


def test_prefilter_fallback_preserves_all():
    results = [
        {"title": "a", "body": "aa"},
        {"title": "b", "body": "bb"},
    ]
    filtered = prefilter_results(results, ["zzz"])
    assert len(filtered) == 2


def test_ddg_query_result_structure():
    results = search_ddg("site:github.com test", "GitHub", "github.com", max_results=1)
    assert isinstance(results, list)
    if results:
        r = results[0]
        for key in ("title", "href", "body", "platform"):
            assert key in r, f"missing: {key}"
        assert not r.get("_from_api", True)


def test_fetch_repo_info_bad_url():
    assert fetch_repo_info("") is None
    assert fetch_repo_info("   ") is None


def test_parse_ai_json_edge_cases():
    assert safe_parse_ai_json(None, dict) is None
    assert safe_parse_ai_json("", dict) is None
    assert safe_parse_ai_json("not json", dict) is None


def test_expand_query_english_passthrough():
    from main import expand_query
    result = expand_query("web scraper python")
    assert result["en_query"] is not None
    assert result["original"] == "web scraper python"


def test_expand_query_french():
    from main import expand_query
    result = expand_query("outil de compression")
    assert result is not None
    assert result["en_query"] is not None


def test_expand_query_returns_all_keys():
    from main import expand_query
    result = expand_query("test")
    for key in ("sub_queries", "en_query", "alt_queries", "keywords", "language", "type", "original", "translated"):
        assert key in result, f"missing: {key}"
