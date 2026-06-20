import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.config import TIMEOUTS


def search_pypi(query: str, max_results: int = 4) -> list:
    try:
        r = requests.get(
            "https://pypi.org/search/",
            params={"q": query, "page": 1},
            headers={"Accept": "application/json"},
            timeout=TIMEOUTS["api_main"],
        )
        if r.status_code != 200:
            return []

        body = r.text
        import re
        name_pattern = re.compile(r'class="package-snippet"[^>]*>.*?<span[^>]*class="package-snippet__name"[^>]*>([^<]+)', re.DOTALL)
        desc_pattern = re.compile(r'class="package-snippet__description"[^>]*>([^<]+)', re.DOTALL)
        names = name_pattern.findall(body)[:max_results]
        descs = desc_pattern.findall(body)[:max_results]

        if not names:
            return _fallback_xmlrpc(query, max_results)

        results = []
        for i, name in enumerate(names):
            desc = descs[i].strip() if i < len(descs) else ""
            results.append({
                "title": name.strip(),
                "href": f"https://pypi.org/project/{name.strip()}",
                "body": desc,
                "stars": 0,
                "forks": 0,
                "usage": _get_downloads(name.strip()),
                "usage_label": "dl/month",
                "language": "Python",
                "license": "See PyPI",
                "updated": "",
                "platform": "PyPI",
                "_from_api": True,
            })
        return results
    except Exception:
        return _fallback_xmlrpc(query, max_results)


def _get_downloads(name: str) -> int:
    try:
        r = requests.get(
            f"https://pypistats.org/api/packages/{name}/recent",
            timeout=TIMEOUTS["api_fast"],
        )
        if r.status_code == 200:
            return r.json().get("data", {}).get("last_month", 0)
    except Exception:
        pass
    return 0


def _fallback_xmlrpc(query: str, max_results: int) -> list:
    try:
        import xmlrpc.client
        client = xmlrpc.client.ServerProxy("https://pypi.org/pypi")
        hits = client.search({"name": query, "summary": query}, "or")
        names, seen = [], set()
        for h in (hits or [])[:max_results * 2]:
            name = h.get("name", "")
            if name and name not in seen:
                seen.add(name)
                names.append(h)
            if len(names) >= max_results:
                break
        if not names:
            return []
        dl_map = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(_get_downloads, h["name"]): h["name"] for h in names}
            for fut, name in futs.items():
                try:
                    dl_map[name] = fut.result(timeout=5)
                except Exception:
                    dl_map[name] = 0
        results = []
        for h in names:
            name = h.get("name", "")
            results.append({
                "title": name,
                "href": f"https://pypi.org/project/{name}",
                "body": h.get("summary", ""),
                "stars": 0,
                "forks": 0,
                "usage": dl_map.get(name, 0),
                "usage_label": "dl/month",
                "language": "Python",
                "license": "See PyPI",
                "updated": h.get("version", ""),
                "platform": "PyPI",
                "_from_api": True,
            })
        return results
    except Exception:
        return []
