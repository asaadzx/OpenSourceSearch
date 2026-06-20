from ai_backend.ranking import ai_rank_results


def _make_result(title: str, desc: str = "", stars: int = 0, usage: int = 0):
    return {
        "title": title,
        "href": f"https://github.com/{title}",
        "body": desc,
        "stars": stars,
        "forks": 0,
        "usage": usage,
        "usage_label": "watchers",
        "language": "Python",
        "license": "MIT",
        "updated": "2024-01-01",
        "platform": "GitHub",
        "_from_api": True,
    }


def test_rank_empty_results():
    assert ai_rank_results([], "test") == []


def test_rank_single_result():
    results = [_make_result("test/proj", desc="a tool")]
    ranked = ai_rank_results(results, "test")
    assert len(ranked) == 1
    assert "_score" in ranked[0]
    assert "_match_pct" in ranked[0]


def test_rank_results_sorted_by_score():
    results = [
        _make_result("good/match", desc="exact tool match", stars=100, usage=50),
        _make_result("bad/match", desc="unrelated thing", stars=0, usage=0),
    ]
    ranked = ai_rank_results(results, "specific tool")
    assert len(ranked) == 2
    scores = [r["_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_truncates_at_15():
    results = [_make_result(f"proj/{i}") for i in range(30)]
    ranked = ai_rank_results(results, "test")
    assert len(ranked) >= 15


def test_rank_score_ranges():
    results = [
        _make_result("perfect/match", desc="exact match", stars=1000, usage=500),
        _make_result("no/data", desc="", stars=0, usage=0),
    ]
    ranked = ai_rank_results(results, "test")
    for r in ranked:
        assert 0 <= r["_match_pct"] <= 100
        assert 0 <= r["_stars_score"] <= 100
        assert 0 <= r["_usage_score"] <= 100
        assert 0 <= r["_score"] <= 100


def test_rank_higher_stars_higher_score():
    results = [
        _make_result("high/stars", desc="same desc", stars=5000),
        _make_result("low/stars", desc="same desc", stars=1),
    ]
    ranked = ai_rank_results(results, "same desc")
    high = [r for r in ranked if r["title"] == "high/stars"][0]
    low = [r for r in ranked if r["title"] == "low/stars"][0]
    assert high["_stars_score"] >= low["_stars_score"]


def test_rank_missing_fields_dont_crash():
    results = [{"title": "minimal"}]
    ranked = ai_rank_results(results, "test")
    assert len(ranked) == 1
    assert "_score" in ranked[0]


def test_rank_score_components_present():
    r = _make_result("test/proj", desc="desc", stars=100, usage=200)
    ranked = ai_rank_results([r], "test")
    r2 = ranked[0]
    assert "_match_pct" in r2
    assert "_stars_score" in r2
    assert "_usage_score" in r2
    assert "_score" in r2
