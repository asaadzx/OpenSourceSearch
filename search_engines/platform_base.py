from duckduckgo_search import DDGS

import duckduckgo_search.duckduckgo_search as _ddgs_mod
if _ddgs_mod.warnings.simplefilter.__name__ != "_suppress_rename_warning":
    _original_simplefilter = _ddgs_mod.warnings.simplefilter
    def _suppress_rename_warning(action, category=Warning, append=False):
        if action == "always" and category is Warning:
            return
        return _original_simplefilter(action, category, append)
    _ddgs_mod.warnings.simplefilter = _suppress_rename_warning
    _ddgs_mod.DDGS.__init__.__globals__["warnings"].simplefilter = _suppress_rename_warning

from core.config import HEADERS_BROWSER


def search_ddg(query: str, platform_name: str, domain: str, max_results: int = 4) -> list:
    try:
        with DDGS(headers=HEADERS_BROWSER) as ddgs:
            hits = list(ddgs.text(f"site:{domain} {query}", max_results=max_results))
        results = []
        for h in hits:
            results.append({
                "title": h.get("title", ""),
                "href": h.get("href", ""),
                "body": h.get("body", ""),
                "stars": 0,
                "forks": 0,
                "usage": 0,
                "usage_label": "",
                "language": "N/A",
                "license": "Unknown",
                "updated": "",
                "platform": platform_name,
                "_from_api": False,
            })
        return results
    except Exception:
        return []


def smart_deduplicate(results: list) -> list:
    seen_hrefs = set()
    seen_names: dict = {}
    unique = []
    for r in results:
        href = (r.get("href", "") or "").rstrip("/").replace(".git", "").lower()
        name = __import__("re").sub(
            r'[^a-z0-9]', '',
            (r.get("title", "") or "").lower().split("/")[-1],
        )
        if href and href in seen_hrefs:
            idx = next((i for i, u in enumerate(unique) if u.get("href", "").rstrip("/").replace(".git", "").lower() == href), None)
            if idx is not None and (r.get("stars", 0) or 0) > (unique[idx].get("stars", 0) or 0):
                unique[idx] = r
            continue
        if name and name in seen_names:
            idx = seen_names[name]
            if (r.get("stars", 0) or 0) > (unique[idx].get("stars", 0) or 0):
                unique[idx] = r
            continue
        if href:
            seen_hrefs.add(href)
        if name:
            seen_names[name] = len(unique)
        unique.append(r)
    return unique


def prefilter_results(results: list, keywords: list) -> list:
    if not keywords:
        return results
    kw_lower = [k.lower() for k in keywords if len(k) > 2]
    if not kw_lower:
        return results
    filtered = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('body', '')}".lower()
        if any(kw in text for kw in kw_lower):
            filtered.append(r)
    return filtered if len(filtered) >= 3 else results
