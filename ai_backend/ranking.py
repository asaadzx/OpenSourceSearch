import json
import math

from ai_backend.llm_handler import ai_chat, safe_parse_ai_json


def ai_rank_results(results: list, user_description: str) -> list:
    if not results:
        return results

    items = []
    for i, r in enumerate(results[:15]):
        items.append({
            "id": i,
            "name": r.get("title", ""),
            "desc": (r.get("body", "") or "")[:250],
            "stars": r.get("stars", 0) or 0,
            "usage": r.get("usage", 0) or 0,
        })

    ai_prompt = f"""You are an expert software engineer ranking open-source search results.

The user is looking for: "{user_description}"

Scoring scale examples:
- User wants "wifi password cracker", result is "aircrack-ng WPA/WPA2 cracking" -> 97
- User wants "wifi password cracker", result is "hashcat GPU hash cracker" -> 75
- User wants "wifi password cracker", result is "nmap network scanner" -> 25
- User wants "wifi password cracker", result is "flask web framework" -> 2
- User wants "file sync", result is "rclone sync files to cloud" -> 95
- User wants "file sync", result is "rsync fast file transfer" -> 88
- User wants "file sync", result is "git version control" -> 18

Score each tool 0-100 based ONLY on how well its purpose matches what the user wants.
Ignore stars and download counts entirely.

Tools to score:
{json.dumps(items, ensure_ascii=False, indent=2)}

Return ONLY a JSON array, no extra text:
[{{"id": 0, "score": 85}}, {{"id": 1, "score": 42}}, ...]
Include a score for every id from 0 to {len(items) - 1}."""

    scored_map = {}
    ai_raw = ai_chat(ai_prompt)
    scores = safe_parse_ai_json(ai_raw, list)
    if scores:
        try:
            for s in scores:
                scored_map[int(s["id"])] = max(0, min(100, int(s["score"])))
        except Exception:
            pass

    max_stars = max((r.get("stars", 0) or 0 for r in results), default=1) or 1
    max_usage = max((r.get("usage", 0) or 0 for r in results), default=1) or 1

    ranked = []
    for i, r in enumerate(results):
        has_desc = bool((r.get("body", "") or "").strip())
        has_stars = (r.get("stars", 0) or 0) > 0
        default_score = 40 if (has_desc or has_stars) else 15
        desc_score = scored_map.get(i, default_score)
        stars = r.get("stars", 0) or 0
        usage = r.get("usage", 0) or 0
        stars_score = int((math.log1p(stars) / math.log1p(max_stars)) * 100) if stars > 0 else 0
        usage_score = int((math.log1p(usage) / math.log1p(max_usage)) * 100) if usage > 0 else 0
        final = int(0.50 * desc_score + 0.30 * stars_score + 0.20 * usage_score)
        ranked.append({
            **r,
            "_match_pct": desc_score,
            "_stars_score": stars_score,
            "_usage_score": usage_score,
            "_score": final,
        })

    ranked.sort(
        key=lambda x: (x["_score"], x.get("stars", 0) or 0, x.get("usage", 0) or 0),
        reverse=True,
    )
    return ranked
