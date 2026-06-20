import requests

from core.config import TIMEOUTS


def search_huggingface(query: str, max_results: int = 4) -> list:
    try:
        r = requests.get(
            "https://huggingface.co/api/models",
            params={
                "search": query,
                "limit": max_results,
                "sort": "likes",
                "direction": -1,
            },
            timeout=TIMEOUTS["api_main"],
        )
        if r.status_code != 200:
            return []
        results = []
        for item in r.json():
            tags = item.get("tags", [])
            lic = next(
                (t.replace("license:", "") for t in tags if t.startswith("license:")),
                "Unknown",
            )
            results.append({
                "title": item.get("id", ""),
                "href": f"https://huggingface.co/{item.get('id', '')}",
                "body": ", ".join(t for t in tags if not t.startswith("license:"))[:120],
                "stars": item.get("likes", 0),
                "forks": 0,
                "usage": item.get("downloads", 0),
                "usage_label": "downloads",
                "language": "Model",
                "license": lic,
                "updated": item.get("lastModified", "")[:10],
                "platform": "Hugging Face",
                "_from_api": True,
            })
        return results
    except Exception:
        return []
