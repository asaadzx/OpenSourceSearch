import os
import json
import difflib
import tempfile

CACHE_FILE = "query_cache.json"
MAX_WORDS_LIMIT = 100000


def _get_cache_word_count(cache_list: list) -> int:
    total_words = 0
    for entry in cache_list:
        text_to_count = (
            f"{entry.get('original', '')} {entry.get('translated', '')} "
            f"{entry.get('en_query', '')} "
            f"{' '.join(entry.get('alt_queries', []))} "
            f"{' '.join(entry.get('keywords', []))}"
        )
        total_words += len(text_to_count.split())
    return total_words


def lookup_cache(user_input: str, threshold: float = 0.8) -> dict | None:
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cache_list = json.load(f)
        if not isinstance(cache_list, list):
            return None
        best_match = None
        best_ratio = 0.0
        for entry in cache_list:
            orig = entry.get("original", "").lower()
            ratio = difflib.SequenceMatcher(None, user_input.lower(), orig).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = entry
        if best_ratio >= threshold:
            best_match["_match_similarity"] = int(best_ratio * 100)
            return best_match
    except Exception:
        pass
    return None


def _atomic_write_json(path: str, data: list):
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def save_to_cache(entry: dict):
    cache_list = []
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache_list = json.load(f)
            if not isinstance(cache_list, list):
                cache_list = []
        except Exception:
            cache_list = []
    cache_list.append(entry)
    while _get_cache_word_count(cache_list) > MAX_WORDS_LIMIT and len(cache_list) > 1:
        evict_num = max(1, int(len(cache_list) * 0.10))
        cache_list = cache_list[evict_num:]
    try:
        _atomic_write_json(CACHE_FILE, cache_list)
    except Exception:
        pass
