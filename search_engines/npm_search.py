import requests

from core.config import TIMEOUTS


def search_npm(query: str, max_results: int = 4) -> list:
    try:
        r = requests.get(
            "https://registry.npmjs.org/-/v1/search",
            params={
                "text": query,
                "size": max_results,
                "quality": 0.65,
                "popularity": 0.98,
                "maintenance": 0.5,
            },
            timeout=TIMEOUTS["api_main"],
        )
        if r.status_code != 200:
            return []
        results = []
        for obj in r.json().get("objects", []):
            pkg = obj.get("package", {})
            pkg_name = pkg.get("name", "")
            weekly_dl = 0
            try:
                dl_r = requests.get(
                    f"https://api.npmjs.org/downloads/point/last-week/{pkg_name}",
                    timeout=TIMEOUTS["api_fast"],
                )
                if dl_r.status_code == 200:
                    weekly_dl = dl_r.json().get("downloads", 0) or 0
            except Exception:
                pass
            results.append({
                "title": pkg_name,
                "href": pkg.get("links", {}).get("npm", f"https://npmjs.com/package/{pkg_name}"),
                "body": pkg.get("description", ""),
                "stars": 0,
                "forks": 0,
                "usage": weekly_dl,
                "usage_label": "dl/week",
                "language": "JavaScript",
                "license": pkg.get("license", "Unknown"),
                "updated": pkg.get("date", "")[:10],
                "platform": "npm",
                "_from_api": True,
            })
        return results
    except Exception:
        return []
