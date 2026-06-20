import requests

from core.config import TIMEOUTS, HEADERS_BROWSER


def search_docker(query: str, max_results: int = 3) -> list:
    try:
        r = requests.get(
            "https://hub.docker.com/v2/search/repositories/",
            params={"query": query, "page_size": max_results},
            headers=HEADERS_BROWSER,
            timeout=TIMEOUTS["api_main"],
        )
        if r.status_code != 200:
            return []
        results = []
        for item in r.json().get("results", []):
            results.append({
                "title": item.get("repo_name", ""),
                "href": f"https://hub.docker.com/r/{item.get('repo_name', '')}",
                "body": item.get("short_description", ""),
                "stars": item.get("star_count", 0),
                "forks": 0,
                "usage": item.get("pull_count", 0),
                "usage_label": "pulls",
                "language": "Docker",
                "license": "Unknown",
                "updated": item.get("last_updated", "")[:10],
                "platform": "Docker Hub",
                "_from_api": True,
            })
        return results
    except Exception:
        return []
