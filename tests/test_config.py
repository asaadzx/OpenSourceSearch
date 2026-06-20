from core.config import (
    PLATFORMS, TIMEOUTS, LICENSE_MAP, UNKNOWN_LICENSE,
    HEADERS_BROWSER, GITHUB_TOKEN, QUESTIONARY_STYLE,
)


def test_platforms_count():
    assert len(PLATFORMS) == 9


def test_all_platforms_have_required_keys():
    for name, info in PLATFORMS.items():
        assert "domain" in info, f"{name} missing domain"
        assert "api" in info, f"{name} missing api"
        assert info["domain"], f"{name} has empty domain"


def test_platform_names_unique():
    names = list(PLATFORMS.keys())
    assert len(names) == len(set(names))


def test_timeouts_all_positive():
    for key, val in TIMEOUTS.items():
        assert val > 0, f"TIMEOUTS.{key} must be > 0, got {val}"


def test_timeout_keys():
    expected = {"api_fast", "api_main", "ai", "ddg", "translate"}
    assert set(TIMEOUTS.keys()) == expected


def test_license_map_has_common():
    for lic in ("mit", "apache-2.0", "gpl-3.0", "unlicense"):
        assert lic in LICENSE_MAP, f"Missing license: {lic}"


def test_license_entry_structure():
    for key, val in LICENSE_MAP.items():
        for field in ("name", "allowed", "forbidden", "conditions"):
            assert field in val, f"{key} missing '{field}'"


def test_unknown_license_structure():
    for field in ("name", "allowed", "forbidden", "conditions"):
        assert field in UNKNOWN_LICENSE


def test_headers_browser_user_agent():
    ua = HEADERS_BROWSER.get("User-Agent", "")
    assert "Chrome" in ua
    assert "Mobile" in ua


def test_github_token_type():
    assert isinstance(GITHUB_TOKEN, str)


def test_questionary_style_has_entries():
    rules = QUESTIONARY_STYLE.style_rules
    rule_names = {r[0] for r in rules}
    for f in ("qmark", "question", "answer", "pointer", "selected"):
        assert f in rule_names, f"QUESTIONARY_STYLE missing '{f}'"


def test_no_duplicate_license_keys():
    assert len(LICENSE_MAP) == len(set(LICENSE_MAP.keys()))
