from search_engines.github_search import search_github, fetch_repo_info
from search_engines.huggingface_search import search_huggingface
from search_engines.pypi_search import search_pypi
from search_engines.npm_search import search_npm
from search_engines.docker_search import search_docker
from search_engines.platform_base import search_ddg, smart_deduplicate, prefilter_results


def test_search_github_empty_query():
    results = search_github("")
    assert isinstance(results, list)


def test_search_github_returns_list():
    results = search_github("python")
    assert isinstance(results, list)


def test_search_github_result_structure():
    results = search_github("numpy", max_results=1)
    if results:
        r = results[0]
        for key in ("title", "href", "body", "stars", "license", "platform"):
            assert key in r, f"missing key: {key}"
        assert r["platform"] == "GitHub"


def test_search_huggingface():
    results = search_huggingface("bert", max_results=1)
    assert isinstance(results, list)
    if results:
        assert "platform" in results[0]


def test_search_pypi():
    results = search_pypi("requests", max_results=1)
    assert isinstance(results, list)
    if results:
        assert results[0]["platform"] == "PyPI"


def test_search_npm():
    results = search_npm("express", max_results=1)
    assert isinstance(results, list)
    if results:
        assert results[0]["platform"] == "npm"


def test_search_docker():
    results = search_docker("nginx", max_results=1)
    assert isinstance(results, list)
    if results:
        assert results[0]["platform"] == "Docker Hub"


def test_search_ddg_no_results_for_garbage():
    results = search_ddg("xyzzy_nonexistent_12345", "Test", "example.com", max_results=1)
    assert isinstance(results, list)


def test_smart_deduplicate_empty():
    assert smart_deduplicate([]) == []


def test_smart_deduplicate_no_dupes():
    results = [
        {"title": "proj/a", "href": "https://github.com/proj/a", "stars": 10},
        {"title": "proj/b", "href": "https://github.com/proj/b", "stars": 20},
    ]
    deduped = smart_deduplicate(results)
    assert len(deduped) == 2


def test_smart_deduplicate_keeps_higher_stars():
    results = [
        {"title": "owner/repo", "href": "https://github.com/owner/repo", "stars": 5},
        {"title": "owner/repo", "href": "https://github.com/owner/repo", "stars": 100},
    ]
    deduped = smart_deduplicate(results)
    assert len(deduped) == 1
    assert deduped[0]["stars"] == 100


def test_smart_deduplicate_normalizes_url():
    results = [
        {"title": "owner/repo", "href": "https://github.com/owner/repo.git", "stars": 10},
        {"title": "owner/repo", "href": "https://github.com/owner/repo/", "stars": 5},
    ]
    deduped = smart_deduplicate(results)
    assert len(deduped) == 1


def test_prefilter_empty_keywords():
    results = [{"title": "test", "body": "description"}]
    assert prefilter_results(results, []) == results


def test_prefilter_matching():
    results = [
        {"title": "python scraper", "body": "scrape websites with python"},
        {"title": "image editor", "body": "edit photos"},
    ]
    filtered = prefilter_results(results, ["scrape", "python"])
    assert len(filtered) >= 1


def test_prefilter_fallback_when_too_few():
    results = [
        {"title": "cat", "body": "cat pictures"},
        {"title": "dog", "body": "dog walker"},
    ]
    filtered = prefilter_results(results, ["elephant"])
    assert len(filtered) == 2


def test_fetch_repo_info_nonexistent():
    info = fetch_repo_info("nonexistent-owner-12345/nonexistent-repo-67890")
    assert info is None
