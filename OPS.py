
import sys
import os
import re
import json
import math
import warnings
import logging
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, quote
import requests
import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.align import Align
from rich.rule import Rule

import io, contextlib
import difflib

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
os.environ["G4F_QUIET"] = "1"
os.environ["G4F_NO_UPDATE_CHECK"] = "1"

try:
    _devnull_fd = os.open(os.devnull, os.O_WRONLY)
    _stderr_fd  = sys.stderr.fileno()
    _stderr_fd_saved = os.dup(_stderr_fd)
    os.dup2(_devnull_fd, _stderr_fd)
    os.close(_devnull_fd)
except Exception:
    pass
sys.stderr = open(os.devnull, "w")

import types as _types
_fake_g4f_ver = _types.ModuleType("g4f.version")
_fake_g4f_ver.utils = _types.SimpleNamespace(check_pypi_version=lambda: None)
sys.modules.setdefault("g4f.version", _fake_g4f_ver)

# ───────────────────────────────────────────────────────────────
# GLOBAL SETUP
# ───────────────────────────────────────────────────────────────
console = Console()

TIMEOUTS = {
    "api_fast":  5,
    "api_main": 10,
    "ai":       25,
    "ddg":       8,
    "translate": 8,
}

QUESTIONARY_STYLE = Style([
    ("qmark",       "fg:#e5c07b bold"),
    ("question",    "fg:#61afef bold"),
    ("answer",      "fg:#98c379 bold"),
    ("pointer",     "fg:#e06c75 bold"),
    ("highlighted", "fg:#c678dd bold"),
    ("selected",    "fg:#98c379"),
    ("separator",   "fg:#5c6370"),
    ("instruction", "fg:#5c6370 italic"),
    ("text",        "fg:#abb2bf"),
    ("disabled",    "fg:#5c6370 italic"),
])

PLATFORMS = {
    "GitHub":       {"domain": "github.com",       "api": "github"},
    "GitLab":       {"domain": "gitlab.com",        "api": "ddg"},
    "Bitbucket":    {"domain": "bitbucket.org",     "api": "ddg"},
    "Codeberg":     {"domain": "codeberg.org",      "api": "ddg"},
    "Hugging Face": {"domain": "huggingface.co",    "api": "huggingface"},
    "SourceForge":  {"domain": "sourceforge.net",   "api": "ddg"},
    "PyPI":         {"domain": "pypi.org",          "api": "pypi"},
    "npm":          {"domain": "npmjs.com",         "api": "npm"},
    "Docker Hub":   {"domain": "hub.docker.com",    "api": "docker"},
}

LICENSE_MAP = {
    "mit":          {"name": "MIT",         "allowed": "Commercial, Modify, Distribute, Private",          "forbidden": "Liability, Warranty",            "conditions": "Include license notice"},
    "apache-2.0":   {"name": "Apache 2.0",  "allowed": "Commercial, Modify, Distribute, Patent, Private", "forbidden": "Trademark, Liability",           "conditions": "State changes, Include notice"},
    "gpl-3.0":      {"name": "GPL v3",      "allowed": "Commercial, Modify, Distribute, Patent, Private", "forbidden": "Sublicense, Liability",          "conditions": "Disclose source, Same license"},
    "gpl-2.0":      {"name": "GPL v2",      "allowed": "Commercial, Modify, Distribute, Private",         "forbidden": "Sublicense, Liability",          "conditions": "Disclose source, Same license"},
    "lgpl-2.1":     {"name": "LGPL 2.1",    "allowed": "Commercial, Modify, Distribute, Private",         "forbidden": "Liability, Warranty",            "conditions": "Disclose library source changes"},
    "bsd-2-clause": {"name": "BSD 2-Clause","allowed": "Commercial, Modify, Distribute, Private",         "forbidden": "Liability, Warranty",            "conditions": "Include license notice"},
    "bsd-3-clause": {"name": "BSD 3-Clause","allowed": "Commercial, Modify, Distribute, Private",         "forbidden": "Liability, Warranty, Endorsement","conditions": "Include license notice"},
    "mpl-2.0":      {"name": "MPL 2.0",     "allowed": "Commercial, Modify, Distribute, Patent, Private", "forbidden": "Liability, Warranty",            "conditions": "Disclose source, Include notice"},
    "agpl-3.0":     {"name": "AGPL v3",     "allowed": "Commercial, Modify, Distribute, Patent, Private", "forbidden": "Sublicense, Liability",          "conditions": "Disclose source (incl. network use)"},
    "unlicense":    {"name": "Unlicense",   "allowed": "Everything — public domain",                      "forbidden": "Nothing",                        "conditions": "None"},
    "isc":          {"name": "ISC",         "allowed": "Commercial, Modify, Distribute, Private",         "forbidden": "Liability, Warranty",            "conditions": "Include license notice"},
    "cc0-1.0":      {"name": "CC0 1.0",     "allowed": "Everything — public domain",                      "forbidden": "Nothing",                        "conditions": "None"},
}
UNKNOWN_LICENSE = {"name": "Unknown", "allowed": "Check project page", "forbidden": "Possibly all rights reserved", "conditions": "Unknown"}

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# ───────────────────────────────────────────────────────────────
# CACHE IMPLEMENTATION
# ───────────────────────────────────────────────────────────────
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

def _lookup_cache(user_input: str, threshold: float = 0.8) -> dict:
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

def _save_to_cache(entry: dict):
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
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_list, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ───────────────────────────────────────────────────────────────
# LOGO
# ───────────────────────────────────────────────────────────────
def print_logo():
    console.print()
    lines = [
        " [bold bright_green] ██████╗ ██████╗ ███████╗[/]",
        " [bold bright_green]██╔═══██╗██╔══██╗██╔════╝[/]",
        " [bold bright_green]██║   ██║██████╔╝███████╗[/]",
        " [bold bright_green]██║   ██║██╔═══╝ ╚════██║[/]",
        " [bold bright_green]╚██████╔╝██║     ███████║[/]",
        " [bold bright_green] ╚═════╝ ╚═╝     ╚══════╝[/]",
    ]
    for line in lines:
        console.print(line)
    console.print(Text("  open source search", style="dim white"))
    console.print()
    console.print(Panel.fit(
        Align.center(Text("Hybrid search: Direct APIs + DDG fallback | AI query expansion + AI ranking", style="dim cyan")),
        border_style="bright_black",
        padding=(0, 2),
    ))
    console.print()

# ───────────────────────────────────────────────────────────────
# LANGUAGE DETECTION
# ───────────────────────────────────────────────────────────────
def detect_language(text: str) -> str:
    return "ar" if re.search(r'[\u0600-\u06FF]+', text) else "en"

# ───────────────────────────────────────────────────────────────
# AI BACKENDS
# ───────────────────────────────────────────────────────────────
_JUNK_PATTERNS = re.compile(
    r"(sorry|cannot|i can.t|as an ai|i don.t|unavailable|"
    r"i'm not able|i am not able|i cannot|not possible|i apologize)",
    re.IGNORECASE
)

def _is_valid_ai_response(text: str, min_len: int = 20) -> bool:
    if not text or len(text.strip()) < min_len:
        return False
    if _JUNK_PATTERNS.search(text[:150]):
        return False
    return True

_AI_CACHE: dict = {}
_CACHE_TTL = 300

def _try_g4f(prompt: str) -> str:
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            import g4f
            models = [
                g4f.models.default,
                "gpt-4o-mini",
                "gpt-4o",
                "gpt-4",
                "gpt-3.5-turbo",
                "claude-3-haiku",
                "llama-3-70b"
            ]
            for model in models:
                try:
                    result = g4f.ChatCompletion.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    result_str = str(result).strip()
                    if result_str and _is_valid_ai_response(result_str):
                        return result_str
                except Exception:
                    continue
    except Exception:
        pass
    return ""

def _try_g4f_mini(prompt: str) -> str:
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            import g4f
            result = g4f.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            result_str = str(result).strip()
            if result_str and _is_valid_ai_response(result_str):
                return result_str
    except Exception:
        pass
    return ""

def _try_ddgs_chat(prompt: str) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return ddgs.chat(prompt, model="gpt-4o-mini") or ""
    except Exception:
        return ""

def _try_pollinations(prompt: str) -> str:
    try:
        r = requests.post(
            "https://text.pollinations.ai/openai",
            json={"model": "openai", "messages": [{"role": "user", "content": prompt}], "seed": 42},
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUTS["ai"],
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        pass
    try:
        r = requests.get(f"https://text.pollinations.ai/{quote(prompt[:400])}", timeout=TIMEOUTS["ai"])
        if r.status_code == 200 and len(r.text) > 5:
            return r.text.strip()
    except Exception:
        pass
    return ""

def ai_chat(prompt: str, min_len: int = 20) -> str:
    cache_key = hashlib.md5(prompt.encode()).hexdigest()
    if cache_key in _AI_CACHE:
        cached_result, ts = _AI_CACHE[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return cached_result
    for fn in (_try_g4f, _try_g4f_mini, _try_ddgs_chat, _try_pollinations):
        r = fn(prompt)
        if _is_valid_ai_response(r, min_len):
            _AI_CACHE[cache_key] = (r, time.time())
            return r
    return ""

# ───────────────────────────────────────────────────────────────
# JSON PARSER
# ───────────────────────────────────────────────────────────────
def safe_parse_ai_json(raw: str, expected_type=dict):
    if not raw:
        return None
    clean = re.sub(r'```(?:json)?|```', '', raw).strip()
    try:
        result = json.loads(clean)
        if isinstance(result, expected_type):
            return result
    except Exception:
        pass
    pattern = r'\[.*?\]' if expected_type == list else r'\{.*?\}'
    match = re.search(pattern, clean, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, expected_type):
                return result
        except Exception:
            pass
    try:
        fixed = re.sub(r',\s*([}\]])', r'\1', clean)
        result = json.loads(fixed)
        if isinstance(result, expected_type):
            return result
    except Exception:
        pass
    try:
        open_ch  = '[' if expected_type == list else '{'
        close_ch = ']' if expected_type == list else '}'
        depth, start = 0, -1
        for idx, ch in enumerate(clean):
            if ch == open_ch:
                if depth == 0:
                    start = idx
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0 and start != -1:
                    result = json.loads(clean[start:idx+1])
                    if isinstance(result, expected_type):
                        return result
                    break
    except Exception:
        pass
    return None

# ───────────────────────────────────────────────────────────────
# TRANSLATION
# ───────────────────────────────────────────────────────────────
_AR_FALLBACK = {
    "تخزين سحابي مجاني": "free cloud storage",
    "تخزين سحابي": "cloud storage",
    "تخزين": "storage", "سحابي": "cloud", "مجاني": "free",
    "ذكاء اصطناعي": "artificial intelligence",
    "تعلم آلي": "machine learning",
    "واجهة برمجة": "API",
    "سطر الأوامر": "CLI",
    "مفتوح المصدر": "open source",
    "نسخ احتياطي": "backup",
    "قاعدة بيانات": "database",
    "إطار عمل": "framework",
    "لوحة تحكم": "dashboard",
    "جدار ناري": "firewall",
    "هندسة عكسية": "reverse engineering",
    "اختبار اختراق": "penetration testing",
    "شبكة لاسلكية": "wireless network",
    "كلمة مرور": "password",
    "بحث": "search", "ترجمة": "translation",
    "شبكة": "network", "واجهة": "interface",
    "تطبيق": "application", "برنامج": "software",
    "أداة": "tool", "مكتبة": "library",
    "خادم": "server", "عميل": "client",
    "ملفات": "files", "ملف": "file",
    "صور": "images", "صورة": "image",
    "فيديو": "video", "صوت": "audio",
    "نص": "text", "بيانات": "data",
    "أمان": "security", "تشفير": "encryption",
    "ضغط": "compression", "مزامنة": "sync",
    "مشاركة": "sharing", "رفع": "upload",
    "تنزيل": "download", "تحليل": "analytics",
    "مراقبة": "monitoring", "نشر": "deployment",
    "حاويات": "containers", "أتمتة": "automation",
    "اختبار": "testing", "توثيق": "documentation",
    "رسم": "drawing", "خريطة": "map",
    "تقويم": "calendar", "مهام": "tasks",
    "ملاحظات": "notes", "دردشة": "chat",
    "بريد": "email", "إشعارات": "notifications",
    "تقارير": "reports", "فاتورة": "invoice",
    "دفع": "payment", "تسوق": "shopping",
    "موقع": "website", "وب": "web",
    "جوال": "mobile", "سطح مكتب": "desktop",
    "اختراق": "penetration testing",
    "واي فاي": "wifi", "وايفاي": "wifi",
    "تخمين": "brute force", "مسح": "scanning",
    "ثغرة": "vulnerability", "هجوم": "attack",
    "بروكسي": "proxy", "حزم": "packets",
    "استنشاق": "sniffing",
}

def _translate_ar_fallback(text: str) -> str:
    result = text.strip()
    for ar, en in sorted(_AR_FALLBACK.items(), key=lambda x: -len(x[0])):
        result = result.replace(ar, en)
    result = re.sub(r'[\u0600-\u06FF]+', '', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result

def translate_to_english(text: str) -> str:
    if detect_language(text) == "en":
        return text

    # 1. Google Translate
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text[:500]},
            headers=HEADERS_BROWSER,
            timeout=TIMEOUTS["translate"],
        )
        if r.status_code == 200:
            data = r.json()
            t = "".join(part[0] for part in data[0] if part and part[0])
            if t and detect_language(t) == "en":
                return t.strip()
    except Exception:
        pass

    # 2. deep_translator
    try:
        from deep_translator import GoogleTranslator
        r = GoogleTranslator(source="auto", target="en").translate(text)
        if r and r.strip() and detect_language(r.strip()) == "en":
            return r.strip()
    except Exception:
        pass

    # 3. MyMemory
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": "ar|en"},
            headers=HEADERS_BROWSER,
            timeout=TIMEOUTS["translate"],
        )
        if r.status_code == 200:
            t = r.json().get("responseData", {}).get("translatedText", "")
            if t and detect_language(t) == "en" and t.upper() != text.upper():
                return t.strip()
    except Exception:
        pass

    # 4. Lingva
    try:
        r = requests.get(
            f"https://lingva.ml/api/v1/ar/en/{quote(text[:500])}",
            headers=HEADERS_BROWSER,
            timeout=TIMEOUTS["translate"],
        )
        if r.status_code == 200:
            t = r.json().get("translation", "")
            if t and detect_language(t) == "en":
                return t.strip()
    except Exception:
        pass

    # 5. Fallback dictionary
    fallback = _translate_ar_fallback(text)
    if fallback and any(c.isascii() and c.isalpha() for c in fallback):
        return fallback

    return text

def translate_text(text: str, target_lang: str) -> str:
    # 1. Google Translate
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": target_lang[:5], "dt": "t", "q": text[:1000]},
            headers=HEADERS_BROWSER,
            timeout=TIMEOUTS["translate"],
        )
        if r.status_code == 200:
            data = r.json()
            t = "".join(part[0] for part in data[0] if part and part[0])
            if t and t.strip():
                return t.strip()
    except Exception:
        pass

    # 2. MyMemory
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:500], "langpair": f"en|{target_lang[:2]}"},
            headers=HEADERS_BROWSER,
            timeout=TIMEOUTS["translate"],
        )
        if r.status_code == 200:
            t = r.json().get("responseData", {}).get("translatedText", "")
            if t and t.strip() and t.upper() != text.upper():
                return t.strip()
    except Exception:
        pass

    # 3. AI translation as last resort
    result = ai_chat(
        f"Translate the following text to {target_lang}. "
        f"Return only the translation, nothing else.\n\n{text}"
    )
    return result if result else text

# ───────────────────────────────────────────────────────────────
# QUERY EXPANSION
# ───────────────────────────────────────────────────────────────
_STOPWORDS = {
    "a","an","the","is","are","was","were","be","been","being",
    "have","has","had","do","does","did","will","would","could",
    "should","may","might","shall","can","need","dare","ought",
    "used","that","this","these","those","it","its","i","me","my",
    "we","our","you","your","he","she","they","their","them","us",
    "for","to","of","in","on","at","by","with","from","into","like",
    "want","find","get","use","using","help","helps","allow","allows",
    "let","lets","give","gives","make","makes","look","looking",
    "just","very","also","really","some","any","all","more","most",
    "much","many","than","then","when","where","which","who","how",
    "what","why","easy","easily","simple","quickly","fast","tool",
    "program","software","application","something","need","needs",
}

_TECH_MAP = {
    "website": "web", "websites": "web", "web": "web",
    "program": "app", "programming": "dev",
    "build": "builder", "create": "generator", "make": "builder",
    "fast": "performance", "data": "data",
    "database": "database", "store": "storage", "storage": "storage",
    "cloud": "cloud", "file": "file", "image": "image",
    "video": "video", "audio": "audio",
    "chat": "chat", "email": "email", "search": "search",
    "machine learning": "ml",
    "ai": "ai", "api": "api",
    "server": "server", "deploy": "deploy",
    "monitor": "monitor", "test": "test",
    "scrape": "scrape", "scraping": "scrape",
    "download": "downloader", "upload": "upload",
    "convert": "converter", "parse": "parser",
    "encrypt": "security", "backup": "backup",
    "sync": "sync", "task": "task", "schedule": "scheduler",
    "graph": "graph", "chart": "chart",
    "pdf": "pdf", "excel": "spreadsheet",
    "markdown": "markdown", "cli": "cli",
    "game": "game", "mobile": "mobile",
    "desktop": "gui", "docker": "docker",
    "kubernetes": "k8s",
    "penetration testing": "pentest",
    "wifi": "wifi",
    "wireless": "wireless",
    "password": "password",
    "vulnerability": "vulnerability",
    "scanning": "scanner",
    "sniffing": "sniffer",
    "forensics": "forensics",
    "reverse engineering": "reverse",
    "wpa": "wpa",
    "brute force": "brute-force",
    "osint": "osint",
    "recon": "recon",
}

def _smart_fallback_query(translated: str) -> str:
    words = translated.lower().split()
    clean_words = []
    for w in words:
        clean_w = re.sub(r'[^a-z0-9]', '', w)
        if clean_w and clean_w not in _STOPWORDS:
            clean_words.append(clean_w)
    return " ".join(clean_words) if clean_words else translated

def expand_query(user_input: str) -> dict:
    cached_result = _lookup_cache(user_input)
    if cached_result:
        console.print(
            f"  [green]Using cached result (Similarity match: {cached_result['_match_similarity']}%)[/]\n"
            f"  [dim]q1:[/] [white]{cached_result['en_query']}[/]"
        )
        return cached_result

    translated = user_input
    if detect_language(user_input) != "en":
        with Progress(SpinnerColumn(), TextColumn("[dim]Translating..."), transient=True) as p:
            p.add_task("", total=None)
            translated = translate_to_english(user_input)
        if translated != user_input:
            console.print(f"[dim]Translated:[/] [italic white]{translated}[/]")

    ai_prompt = f"""You are a world-class Software Architect and Search Engineer.
Your goal is to translate user descriptions into highly precise technical search terms.

User Request: "{translated}"

Instructions:
1. Detect if the user description contains MULTIPLE independent technical tasks or tools (e.g., "scraping and directory creation", "pdf parser and spreadsheet generator").
2. If multiple tasks are detected:
   - Break them down into distinct, individual search concepts and place them in the "sub_queries" array.
   - Example: "scrape web and make folders" -> "sub_queries": ["web scraper crawler", "directory creation filesystem automation"]
3. If it is a single unified task, "sub_queries" should contain just one main technical query.
4. Keep query1 and query2 extremely concise (max 3-4 words).

Return ONLY valid JSON:
{{
  "sub_queries": ["concept 1", "concept 2"],
  "query1": "primary unified search query (2-3 words)",
  "query2": "alternative technical synonyms (3-4 words)",
  "query3": "related package category (2-3 words)",
  "keywords": ["key1", "key2", "key3"],
  "language": "Any",
  "type": "any"
}}"""

    ai_raw = ai_chat(ai_prompt)
    parsed = safe_parse_ai_json(ai_raw, dict)

    if parsed:
        sub_queries = parsed.get("sub_queries", [])
        q1 = parsed.get("query1", "").strip()
        q2 = parsed.get("query2", "").strip()
        q3 = parsed.get("query3", "").strip()
        
        if q1 and detect_language(q1) == "en":
            if not sub_queries:
                sub_queries = [q1]
                
            console.print(
                f"  [dim]Sub-queries detected:[/] [cyan]{', '.join(sub_queries)}[/]\n"
                f"  [dim]q1:[/] [white]{q1}[/]\n"
                f"  [dim]q2:[/] [white]{q2}[/]\n"
                f"  [dim]q3:[/] [white]{q3}[/]"
            )
            result_dict = {
                "sub_queries":  sub_queries,
                "en_query":    q1,
                "alt_queries": [x for x in [q2, q3] if x and detect_language(x) == "en"],
                "keywords":    parsed.get("keywords", translated.split()[:5]),
                "language":    parsed.get("language", "Any"),
                "type":        parsed.get("type", "any"),
                "original":    user_input,
                "translated":  translated,
            }
            _save_to_cache(result_dict)
            return result_dict

    fallback_query = _smart_fallback_query(translated)
    console.print(f"  [dim]fallback query:[/] [white]{fallback_query}[/]")
    return {
        "sub_queries":  [fallback_query],
        "en_query":    fallback_query,
        "alt_queries": [],
        "keywords":    fallback_query.split()[:5],
        "language":    "Any",
        "type":        "any",
        "original":    user_input,
        "translated":  translated,
    }

# ───────────────────────────────────────────────────────────────
# PRE-FILTER
# ───────────────────────────────────────────────────────────────
def _prefilter_results(results: list, keywords: list) -> list:
    if not keywords:
        return results
    kw_lower = [k.lower() for k in keywords if len(k) > 2]
    if not kw_lower:
        return results
    filtered = []
    for r in results:
        text = f"{r.get('title','')} {r.get('body','')}".lower()
        if any(kw in text for kw in kw_lower):
            filtered.append(r)
    return filtered if len(filtered) >= 3 else results

# ───────────────────────────────────────────────────────────────
# AI RANKING
# ───────────────────────────────────────────────────────────────
def ai_rank_results(results: list, user_description: str) -> list:
    if not results:
        return results

    items = []
    for i, r in enumerate(results[:15]):
        items.append({
            "id":    i,
            "name":  r.get("title", ""),
            "desc":  (r.get("body", "") or "")[:250],
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
Include a score for every id from 0 to {len(items)-1}."""

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
        has_desc  = bool((r.get("body", "") or "").strip())
        has_stars = (r.get("stars", 0) or 0) > 0
        default_score = 40 if (has_desc or has_stars) else 15
        desc_score  = scored_map.get(i, default_score)
        stars       = r.get("stars", 0) or 0
        usage       = r.get("usage",  0) or 0
        stars_score = int((math.log1p(stars) / math.log1p(max_stars)) * 100) if stars > 0 else 0
        usage_score = int((math.log1p(usage) / math.log1p(max_usage)) * 100) if usage > 0 else 0
        final = int(0.50 * desc_score + 0.30 * stars_score + 0.20 * usage_score)
        ranked.append({
            **r,
            "_match_pct":   desc_score,
            "_stars_score": stars_score,
            "_usage_score": usage_score,
            "_score":       final,
        })

    ranked.sort(
        key=lambda x: (x["_score"], x.get("stars", 0) or 0, x.get("usage", 0) or 0),
        reverse=True,
    )
    return ranked

# ───────────────────────────────────────────────────────────────
# SEARCH FUNCTIONS
# ───────────────────────────────────────────────────────────────
def search_github(query: str, prog_lang: str = "Any", max_results: int = 8) -> list:
    try:
        q = query
        if prog_lang and prog_lang.lower() not in ("any", ""):
            q += f" language:{prog_lang}"
        q += " pushed:>2023-01-01 fork:false"
        params = {"q": q, "sort": "stars", "order": "desc", "per_page": max_results}
        r = requests.get(
            "https://api.github.com/search/repositories",
            params=params,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=TIMEOUTS["api_main"],
        )
        if r.status_code != 200:
            return []
        results = []
        for item in r.json().get("items", []):
            results.append({
                "title":       item["full_name"],
                "href":        item["html_url"],
                "body":        item.get("description", "") or "",
                "stars":       item.get("stargazers_count", 0),
                "forks":       item.get("forks_count", 0),
                "usage":       item.get("watchers_count", 0),
                "usage_label": "watchers",
                "language":    item.get("language") or "N/A",
                "license":     (item.get("license") or {}).get("spdx_id", "Unknown"),
                "updated":     item.get("pushed_at", "")[:10],
                "platform":    "GitHub",
                "_from_api":   True,
            })
        return results
    except Exception:
        return []

def search_huggingface(query: str, max_results: int = 4) -> list:
    try:
        r = requests.get(
            "https://huggingface.co/api/models",
            params={"search": query, "limit": max_results, "sort": "likes", "direction": -1},
            timeout=TIMEOUTS["api_main"],
        )
        if r.status_code != 200:
            return []
        results = []
        for item in r.json():
            tags = item.get("tags", [])
            lic = next((t.replace("license:", "") for t in tags if t.startswith("license:")), "Unknown")
            results.append({
                "title":       item.get("id", ""),
                "href":        f"https://huggingface.co/{item.get('id', '')}",
                "body":        ", ".join(t for t in tags if not t.startswith("license:"))[:120],
                "stars":       item.get("likes", 0),
                "forks":       0,
                "usage":       item.get("downloads", 0),
                "usage_label": "downloads",
                "language":    "Model",
                "license":     lic,
                "updated":     item.get("lastModified", "")[:10],
                "platform":    "Hugging Face",
                "_from_api":   True,
            })
        return results
    except Exception:
        return []

def search_pypi(query: str, max_results: int = 4) -> list:
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

        def _get_downloads(name):
            try:
                ps = requests.get(
                    f"https://pypistats.org/api/packages/{name}/recent",
                    timeout=TIMEOUTS["api_fast"],
                )
                return ps.json().get("data", {}).get("last_month", 0) if ps.ok else 0
            except Exception:
                return 0

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
                "title":       name,
                "href":        f"https://pypi.org/project/{name}",
                "body":        h.get("summary", ""),
                "stars":       0,
                "forks":       0,
                "usage":       dl_map.get(name, 0),
                "usage_label": "dl/month",
                "language":    "Python",
                "license":     "See PyPI",
                "updated":     h.get("version", ""),
                "platform":    "PyPI",
                "_from_api":   True,
            })
        return results
    except Exception:
        return []

def search_npm(query: str, max_results: int = 4) -> list:
    try:
        r = requests.get(
            "https://registry.npmjs.org/-/v1/search",
            params={"text": query, "size": max_results, "quality": 0.65, "popularity": 0.98, "maintenance": 0.5},
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
                "title":       pkg_name,
                "href":        pkg.get("links", {}).get("npm", f"https://npmjs.com/package/{pkg_name}"),
                "body":        pkg.get("description", ""),
                "stars":       0,
                "forks":       0,
                "usage":       weekly_dl,
                "usage_label": "dl/week",
                "language":    "JavaScript",
                "license":     pkg.get("license", "Unknown"),
                "updated":     pkg.get("date", "")[:10],
                "platform":    "npm",
                "_from_api":   True,
            })
        return results
    except Exception:
        return []

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
                "title":       item.get("repo_name", ""),
                "href":        f"https://hub.docker.com/r/{item.get('repo_name','')}",
                "body":        item.get("short_description", ""),
                "stars":       item.get("star_count", 0),
                "forks":       0,
                "usage":       item.get("pull_count", 0),
                "usage_label": "pulls",
                "language":    "Docker",
                "license":     "Unknown",
                "updated":     item.get("last_updated", "")[:10],
                "platform":    "Docker Hub",
                "_from_api":   True,
            })
        return results
    except Exception:
        return []

def search_ddg(query: str, platform_name: str, domain: str, max_results: int = 4) -> list:
    try:
        from duckduckgo_search import DDGS
        with DDGS(headers=HEADERS_BROWSER) as ddgs:
            hits = list(ddgs.text(f"site:{domain} {query}", max_results=max_results))
        results = []
        for h in hits:
            results.append({
                "title":    h.get("title", ""),
                "href":     h.get("href", ""),
                "body":     h.get("body", ""),
                "stars":    0,
                "forks":    0,
                "language": "N/A",
                "license":  "Unknown",
                "updated":  "",
                "platform": platform_name,
                "_from_api": False,
            })
        return results
    except Exception:
        return []

# ───────────────────────────────────────────────────────────────
# SMART DEDUPLICATION
# ───────────────────────────────────────────────────────────────
def _smart_deduplicate(results: list) -> list:
    seen_hrefs = set()
    seen_names: dict = {}
    unique = []
    for r in results:
        href = (r.get("href", "") or "").rstrip("/").replace(".git", "").lower()
        name = re.sub(r'[^a-z0-9]', '',
            (r.get("title", "") or "").lower().split("/")[-1])
        if href and href in seen_hrefs:
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

# ───────────────────────────────────────────────────────────────
# MULTI-PLATFORM SEARCH
# ───────────────────────────────────────────────────────────────
def search_all(query_info: dict, selected_platforms: list, max_per: int = 6) -> list:
    sub_queries = query_info.get("sub_queries", [])
    if not sub_queries:
        sub_queries = [query_info["en_query"]]
        
    primary_list = sub_queries
    if len(sub_queries) == 1:
        primary_list = sub_queries + query_info.get("alt_queries", [])
        
    lang = query_info.get("language", "Any")
    all_results = []
    MIN_API_RESULTS = 3
    MAX_TOTAL_WAIT  = 25

    def _run_api(api_type, q, lang, name, domain, n):
        try:
            if api_type == "github":      return search_github(q, lang, n)
            elif api_type == "huggingface": return search_huggingface(q, n)
            elif api_type == "pypi":       return search_pypi(q, n)
            elif api_type == "npm":        return search_npm(q, n)
            elif api_type == "docker":     return search_docker(q, n)
            elif domain:                   return search_ddg(q, name, domain, n)
        except Exception:
            pass
        return []

    def _search_platform_for_query(name, q):
        info     = PLATFORMS.get(name, {})
        api_type = info.get("api", "ddg")
        domain   = info.get("domain", "")
        collected = []
        seen_hrefs = set()
        
        res = _run_api(api_type, q, lang, name, domain, max_per)
        for r in res:
            href = r.get("href", "")
            if href and href not in seen_hrefs:
                seen_hrefs.add(href)
                collected.append(r)
                
        if len(collected) < MIN_API_RESULTS and domain and api_type != "ddg":
            ddg = search_ddg(q, name, domain, max_per)
            for r in ddg:
                href = r.get("href", "")
                if href and href not in seen_hrefs:
                    seen_hrefs.add(href)
                    collected.append(r)
        return collected

    start = time.time()
    tasks = []
    for name in selected_platforms:
        for q in primary_list[:4]:
            tasks.append((name, q))
            
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_search_platform_for_query, name, q): (name, q) for name, q in tasks}
        for fut in as_completed(futures, timeout=MAX_TOTAL_WAIT):
            try:
                all_results.extend(fut.result())
            except Exception:
                pass
            if time.time() - start > MAX_TOTAL_WAIT * 0.8 and len(all_results) > 15:
                break

    return _smart_deduplicate(all_results)

# ───────────────────────────────────────────────────────────────
# DISPLAY RESULTS TABLE
# ───────────────────────────────────────────────────────────────
def display_results_table(results: list):
    table = Table(
        box=box.ROUNDED,
        border_style="bright_black",
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    table.add_column("#",           style="dim",           width=3,  no_wrap=True)
    table.add_column("Project",     style="bold white",    min_width=20)
    table.add_column("Platform",    style="cyan",          width=11, no_wrap=True)
    table.add_column("Stars",       style="yellow",        width=10, no_wrap=True)
    table.add_column("Usage",       style="bright_yellow", width=14, no_wrap=True)
    table.add_column("Match%",      style="bright_green",  width=8,  no_wrap=True)
    table.add_column("License",     style="magenta",       width=11, no_wrap=True)
    table.add_column("Language",    style="blue",          width=11, no_wrap=True)
    table.add_column("Description", style="dim white",     min_width=22)

    for i, r in enumerate(results, 1):
        stars = r.get("stars", 0) or 0
        usage = r.get("usage", 0) or 0
        usage_label = r.get("usage_label", "")
        stars_str = f"{stars:,}" if stars else "—"
        usage_str = f"{usage:,} {usage_label}" if usage else "—"
        match_pct = r.get("_match_pct", "—")
        match_str = f"{match_pct}%" if isinstance(match_pct, int) else "—"
        table.add_row(
            str(i),
            r.get("title", ""),
            r.get("platform", ""),
            stars_str,
            usage_str,
            match_str,
            r.get("license", "Unknown") or "Unknown",
            r.get("language", "N/A") or "N/A",
            (r.get("body", "") or "")[:75],
        )
    console.print(table)

# ───────────────────────────────────────────────────────────────
# PROJECT DETAIL ACTIONS
# ───────────────────────────────────────────────────────────────
def fetch_readme(repo_full: str) -> str:
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo_full}/readme",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=TIMEOUTS["api_main"],
        )
        if r.status_code == 200:
            import base64
            content = r.json().get("content", "")
            return base64.b64decode(content).decode("utf-8", errors="ignore")
    except Exception:
        pass
    return ""

def action_open_browser(url: str):
    try:
        import subprocess
        subprocess.Popen(["xdg-open", url], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        console.print(f"[green]Opening:[/] {url}")
    except Exception:
        console.print(f"[yellow]URL:[/] {url}")

def action_summary(result: dict):
    title    = result.get("title", "")
    desc     = result.get("body", "") or ""
    url      = result.get("href", "")
    platform = result.get("platform", "")
    language = result.get("language", "") or ""
    stars    = result.get("stars", 0) or 0
    usage    = result.get("usage", 0) or 0
    usage_lbl= result.get("usage_label", "")
    license_ = result.get("license", "") or ""
    updated  = result.get("updated", "") or ""

    readme = ""
    if "github.com" in url:
        parts = url.replace("https://github.com/", "").strip("/").split("/")
        if len(parts) >= 2:
            readme = fetch_readme("/".join(parts[:2]))[:3000]

    context_parts = []
    if language and language not in ("N/A", "Model"):
        context_parts.append(f"written in {language}")
    if stars > 0:
        context_parts.append(f"{stars:,} GitHub stars")
    if usage > 0 and usage_lbl:
        context_parts.append(f"{usage:,} {usage_lbl}")
    if license_:
        context_parts.append(f"licensed under {license_}")
    if updated:
        context_parts.append(f"last updated {updated}")
    context_str = ", ".join(context_parts) if context_parts else "details unknown"

    proj_type = result.get("type", "") or ""
    if language == "Model" or platform == "Hugging Face":
        angle = "Focus on: what ML task it solves, model architecture if known, dataset it was trained on, and how to use it."
    elif "cli" in proj_type.lower() or "tool" in proj_type.lower():
        angle = "Focus on: what problem it solves, key commands or workflows, who benefits most, and any important limitations."
    elif "library" in proj_type.lower() or "framework" in proj_type.lower():
        angle = "Focus on: what it helps developers build, its API style, ecosystem fit, and who should use it."
    else:
        angle = "Focus on: what it does, main features, who it is for, and any notable highlights or limitations."

    prompt = f"""You are a technical writer summarizing open-source projects for developers.

Project: {title}
Platform: {platform}
Context: {context_str}
Description: {desc}
README excerpt:
{readme}

Write a clear, concise summary in 5-7 sentences. {angle}
Be specific — mention actual feature names, commands, or integrations visible in the README.
Do not repeat the project name more than once. Write in plain English."""

    with Progress(SpinnerColumn(), TextColumn("[cyan]Generating summary..."), transient=True) as p:
        p.add_task("", total=None)
        answer = ai_chat(prompt)

    if not answer:
        console.print("[red]Could not generate summary.[/]")
        return

    console.print(Panel(answer, title=f"[bold cyan]Summary — {title}[/]", border_style="cyan"))

    console.print()
    want_translate = questionary.confirm(
        "Translate this summary to another language?",
        default=False,
        style=QUESTIONARY_STYLE,
    ).ask()

    if want_translate:
        target_lang = questionary.text(
            "Enter target language (e.g. Arabic, French, Spanish, German):",
            style=QUESTIONARY_STYLE,
        ).ask()
        if target_lang and target_lang.strip():
            with Progress(SpinnerColumn(), TextColumn("[cyan]Translating..."), transient=True) as p:
                p.add_task("", total=None)
                translated_summary = translate_text(answer, target_lang.strip())
            if translated_summary and translated_summary != answer:
                console.print(Panel(
                    translated_summary,
                    title=f"[bold magenta]Summary — {title} ({target_lang.strip()})[/]",
                    border_style="magenta",
                ))

def action_usage(result: dict):
    title    = result.get("title", "")
    desc     = result.get("body", "") or ""
    url      = result.get("href", "")
    platform = result.get("platform", "")
    language = result.get("language", "") or ""
    stars    = result.get("stars", 0) or 0
    license_ = result.get("license", "") or ""

    readme = ""
    if "github.com" in url:
        parts = url.replace("https://github.com/", "").strip("/").split("/")
        if len(parts) >= 2:
            readme = fetch_readme("/".join(parts[:2]))[:3000]

    if platform == "PyPI" or language == "Python":
        install_hint = "Installation is likely via pip. Show: pip install or pip3 install."
    elif platform == "npm" or language == "JavaScript":
        install_hint = "Installation via npm or yarn. Show both if applicable."
    elif platform == "Docker Hub" or language == "Docker":
        install_hint = "Show docker pull and docker run commands with common options."
    elif platform == "Hugging Face" or language == "Model":
        install_hint = "Show how to load the model with transformers or the relevant library."
    elif language == "Go":
        install_hint = "Show go install command."
    elif language == "Rust":
        install_hint = "Show cargo install command."
    else:
        install_hint = "Show the most common installation method for this platform."

    maturity = ""
    if stars > 10000:
        maturity = "This is a well-established project with extensive documentation."
    elif stars > 1000:
        maturity = "This is a moderately popular project."
    else:
        maturity = "This may be a newer or niche project."

    prompt = f"""You are a senior developer writing a quick-start guide.

Project: {title}
Platform: {platform}
Language: {language}
License: {license_}
Description: {desc}
{maturity}
{install_hint}

README:
{readme}

Return ONLY a JSON array of 3-6 steps. Each step:
  "step":    short action label (Install / Configure / Basic usage / Example / etc.)
  "command": exact single-line shell or code command
  "note":    1-2 sentences explaining what this does

Extract commands directly from the README when available.
Return ONLY valid JSON array, no markdown, no extra text."""

    with Progress(SpinnerColumn(), TextColumn("[cyan]Fetching usage info..."), transient=True) as p:
        p.add_task("", total=None)
        answer = ai_chat(prompt)

    steps = safe_parse_ai_json(answer, list) if answer else None

    if steps:
        console.print()
        console.print(Rule(f"[bold yellow]Usage — {title}[/]", style="yellow"))
        for s in steps:
            console.print(f"\n[bold cyan]{s.get('step', 'Step')}[/]")
            if s.get("note"):
                console.print(f"  [dim]{s['note']}[/]")
            if s.get("command"):
                console.print(Panel(
                    f"[bold bright_green]{s['command']}[/]",
                    border_style="green",
                    padding=(0, 2),
                ))
        console.print()
    else:
        if answer:
            console.print(Panel(answer, title=f"[bold yellow]Usage — {title}[/]", border_style="yellow"))
        else:
            console.print("[red]Could not fetch usage info.[/]")

def action_translate_description(result: dict):
    desc = result.get("body", "") or result.get("title", "")
    if not desc:
        console.print("[red]No description to translate.[/]")
        return
    target_lang = questionary.text(
        "Translate description to (e.g. Arabic, French, Spanish, German):",
        style=QUESTIONARY_STYLE,
    ).ask()
    if not target_lang:
        return
    with Progress(SpinnerColumn(), TextColumn("[cyan]Translating..."), transient=True) as p:
        p.add_task("", total=None)
        translated = translate_text(desc, target_lang.strip())
    if translated:
        console.print(Panel(translated, title=f"[bold magenta]Translation ({target_lang})[/]", border_style="magenta"))
    else:
        console.print("[red]Translation failed.[/]")

def action_license_info(result: dict):
    lic_raw = (result.get("license", "") or "").lower().strip()
    info = LICENSE_MAP.get(lic_raw, UNKNOWN_LICENSE)
    t = Table(box=box.SIMPLE, border_style="bright_black", show_header=False)
    t.add_column("Field", style="bold cyan", width=14)
    t.add_column("Value", style="white")
    t.add_row("License",    info["name"])
    t.add_row("Allowed",    info["allowed"])
    t.add_row("Forbidden",  info["forbidden"])
    t.add_row("Conditions", info["conditions"])
    console.print(Panel(t, title="[bold magenta]License Info[/]", border_style="magenta"))

def action_clone_command(result: dict):
    url = result.get("href", "")
    if "github.com" in url or "gitlab.com" in url or "codeberg.org" in url:
        cmd = f"git clone {url}.git"
    else:
        cmd = f"# Visit: {url}"
    console.print(Panel(f"[bold green]{cmd}[/]", title="Clone Command", border_style="green"))

def action_similar_search(result: dict, selected_platforms: list):
    desc = result.get("body", "") or result.get("title", "")
    console.print(f"\n[cyan]Searching for projects similar to:[/] {result.get('title','')}")
    q_info = expand_query(desc)
    with Progress(SpinnerColumn(), TextColumn("[cyan]Searching..."), transient=True) as p:
        p.add_task("", total=None)
        results = search_all(q_info, selected_platforms)
    if not results:
        console.print("[red]No results found.[/]")
        return
    results = _prefilter_results(results, q_info.get("keywords", []))
    with Progress(SpinnerColumn(), TextColumn("[cyan]AI ranking..."), transient=True) as p:
        p.add_task("", total=None)
        results = ai_rank_results(results, desc)
    display_results_table(results)
    handle_result_selection(results, selected_platforms)

# ───────────────────────────────────────────────────────────────
# COMPARE PROJECTS
# ───────────────────────────────────────────────────────────────
def compare_projects():
    console.print("[cyan]Enter 2-4 project URLs or names to compare (empty line to finish):[/]")
    entries = []
    while len(entries) < 4:
        line = questionary.text(
            f"Project {len(entries)+1} (URL or name):",
            style=QUESTIONARY_STYLE,
        ).ask()
        if not line:
            break
        entries.append(line.strip())
    if len(entries) < 2:
        console.print("[red]Need at least 2 projects to compare.[/]")
        return

    projects = []
    for entry in entries:
        if entry.startswith("http"):
            parsed = urlparse(entry)
            path_parts = parsed.path.strip("/").split("/")
            p = {
                "title": "/".join(path_parts[:2]), "href": entry,
                "body": "", "stars": 0, "forks": 0,
                "language": "N/A", "license": "Unknown",
                "platform": parsed.netloc, "features": "",
            }
            if "github.com" in parsed.netloc and len(path_parts) >= 2:
                repo = "/".join(path_parts[:2])
                try:
                    r = requests.get(
                        f"https://api.github.com/repos/{repo}",
                        headers={"Accept": "application/vnd.github.v3+json"},
                        timeout=TIMEOUTS["api_main"],
                    )
                    if r.status_code == 200:
                        d = r.json()
                        p.update({
                            "title":    d.get("full_name", p["title"]),
                            "body":     d.get("description", "") or "",
                            "stars":    d.get("stargazers_count", 0),
                            "forks":    d.get("forks_count", 0),
                            "language": d.get("language") or "N/A",
                            "license":  (d.get("license") or {}).get("spdx_id", "Unknown"),
                        })
                except Exception:
                    pass
        else:
            p = {
                "title": entry, "href": "", "body": "",
                "stars": 0, "forks": 0, "language": "N/A",
                "license": "Unknown", "platform": "Unknown", "features": "",
            }
        projects.append(p)

    console.print("[dim]Fetching key features for each project...[/]")
    for p in projects:
        readme = ""
        if "github.com" in p.get("href", ""):
            parts = p["href"].replace("https://github.com/", "").strip("/").split("/")
            if len(parts) >= 2:
                readme = fetch_readme("/".join(parts[:2]))[:2000]

        feat_prompt = f"""List the 4-5 most important features of this open-source project.
Project: {p['title']}
Description: {p['body']}
README: {readme}

Return ONLY a JSON array of short feature strings, max 8 words each.
Example: ["Fast async processing", "Built-in REST API", "Docker support", "MIT license"]
Return ONLY valid JSON array, no extra text."""

        with Progress(SpinnerColumn(), TextColumn(f"[dim]Getting features: {p['title'][:25]}...[/]"), transient=True) as pr:
            pr.add_task("", total=None)
            feat_raw = ai_chat(feat_prompt)

        features = safe_parse_ai_json(feat_raw, list)
        if features and isinstance(features, list):
            p["features"] = "\n".join(f"• {f}" for f in features[:5] if isinstance(f, str))
        else:
            p["features"] = (p.get("body", "") or "")[:80] or "—"

    t = Table(
        box=box.ROUNDED,
        border_style="bright_black",
        header_style="bold cyan",
        show_lines=True,
    )
    t.add_column("Field", style="bold cyan", width=14)
    for p in projects:
        t.add_column(p["title"].split("/")[-1], style="white", min_width=18)

    for label, key in [("Platform","platform"),("Stars","stars"),("Forks","forks"),("Language","language"),("License","license")]:
        row = [label]
        for p in projects:
            val = p.get(key, "—")
            if key in ("stars", "forks"):
                val = f"{val:,}" if isinstance(val, int) and val > 0 else "—"
            row.append(str(val) if val else "—")
        t.add_row(*row)

    features_row = ["Key Features"]
    for p in projects:
        features_row.append(p.get("features", "—") or "—")
    t.add_row(*features_row)

    console.print()
    console.print(Panel(t, title="[bold cyan]Project Comparison[/]", border_style="cyan"))

    ai_choice = questionary.confirm("Generate AI comparison summary?", style=QUESTIONARY_STYLE).ask()
    if ai_choice:
        prompt = f"""Compare these open-source projects concisely and technically.
Projects:
{json.dumps([{
    "name": p["title"], "description": p["body"],
    "stars": p["stars"], "language": p["language"],
    "license": p["license"], "features": p["features"],
} for p in projects], indent=2)}

Cover: main differences, strengths, weaknesses, and a clear recommendation for different use cases.
Write in plain English."""

        with Progress(SpinnerColumn(), TextColumn("[cyan]AI comparing..."), transient=True) as prog:
            prog.add_task("", total=None)
            answer = ai_chat(prompt)

        if answer:
            console.print(Panel(answer, title="[bold cyan]AI Comparison[/]", border_style="cyan"))

            console.print()
            want_translate = questionary.confirm(
                "Translate this comparison to another language?",
                default=False,
                style=QUESTIONARY_STYLE,
            ).ask()
            if want_translate:
                target_lang = questionary.text(
                    "Enter target language:",
                    style=QUESTIONARY_STYLE,
                ).ask()
                if target_lang and target_lang.strip():
                    with Progress(SpinnerColumn(), TextColumn("[cyan]Translating..."), transient=True) as p:
                        p.add_task("", total=None)
                        translated_cmp = translate_text(answer, target_lang.strip())
                    if translated_cmp and translated_cmp != answer:
                        console.print(Panel(
                            translated_cmp,
                            title=f"[bold magenta]AI Comparison ({target_lang.strip()})[/]",
                            border_style="magenta",
                        ))

def handle_result_selection(results: list, selected_platforms: list):
    choices = [f"{i}. {r.get('title','')}" for i, r in enumerate(results, 1)]
    choices.append("Back")
    choice = questionary.select(
        "Select a project:",
        choices=choices,
        style=QUESTIONARY_STYLE,
    ).ask()
    if not choice or choice == "Back":
        return
    idx = int(choice.split(".")[0]) - 1
    result = results[idx]

    console.print()
    console.print(Panel(
        f"[bold white]{result.get('title','')}[/]\n"
        f"[dim]{result.get('href','')}[/]\n\n"
        f"{result.get('body','')}",
        title=f"[cyan]{result.get('platform','')}[/]",
        border_style="bright_black",
    ))

    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "Summary",
                "Usage",
                "Translate description",
                "License info",
                "Clone command",
                "Find similar projects",
                "Open in browser",
                "Back",
            ],
            style=QUESTIONARY_STYLE,
        ).ask()

        if not action or action == "Back":
            break
        elif action == "Summary":
            action_summary(result)
        elif action == "Usage":
            action_usage(result)
            break
        elif action == "Translate description":
            action_translate_description(result)
        elif action == "License info":
            action_license_info(result)
        elif action == "Clone command":
            action_clone_command(result)
        elif action == "Find similar projects":
            action_similar_search(result, selected_platforms)
            break
        elif action == "Open in browser":
            action_open_browser(result.get("href", ""))

# ───────────────────────────────────────────────────────────────
# ANALYZE PROJECT BY URL
# ───────────────────────────────────────────────────────────────
def analyze_by_url():
    url = questionary.text("Enter project URL:", style=QUESTIONARY_STYLE).ask()
    if not url:
        return
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    result = {
        "title":     "/".join(path_parts[:2]) if len(path_parts) >= 2 else parsed.netloc,
        "href":      url,
        "body":      "",
        "stars":     0,
        "forks":     0,
        "language":  "N/A",
        "license":   "Unknown",
        "updated":   "",
        "platform":  parsed.netloc,
        "_match_pct": "—",
    }

    if "github.com" in parsed.netloc and len(path_parts) >= 2:
        repo = "/".join(path_parts[:2])
        try:
            r = requests.get(
                f"https://api.github.com/repos/{repo}",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=TIMEOUTS["api_main"],
            )
            if r.status_code == 200:
                d = r.json()
                result.update({
                    "title":    d.get("full_name", result["title"]),
                    "body":     d.get("description", "") or "",
                    "stars":    d.get("stargazers_count", 0),
                    "forks":    d.get("forks_count", 0),
                    "language": d.get("language") or "N/A",
                    "license":  (d.get("license") or {}).get("spdx_id", "Unknown"),
                    "updated":  d.get("pushed_at", "")[:10],
                })
        except Exception:
            pass

    console.print()
    console.print(Panel(
        f"[bold white]{result['title']}[/]\n"
        f"[dim]{result['href']}[/]\n\n"
        f"{result['body']}\n\n"
        f"Stars: [yellow]{result['stars']:,}[/]  |  "
        f"Forks: [blue]{result['forks']:,}[/]  |  "
        f"Language: [cyan]{result['language']}[/]  |  "
        f"License: [magenta]{result['license']}[/]",
        title="[cyan]Project Info[/]",
        border_style="bright_black",
    ))

    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "Summary",
                "Usage",
                "Translate description",
                "License info",
                "Clone command",
                "Open in browser",
                "Back",
            ],
            style=QUESTIONARY_STYLE,
        ).ask()
        if not action or action == "Back":
            break
        elif action == "Summary":
            action_summary(result)
        elif action == "Usage":
            action_usage(result)
            break
        elif action == "Translate description":
            action_translate_description(result)
        elif action == "License info":
            action_license_info(result)
        elif action == "Clone command":
            action_clone_command(result)
        elif action == "Open in browser":
            action_open_browser(result["href"])

# ───────────────────────────────────────────────────────────────
# SEARCH FLOW
# ───────────────────────────────────────────────────────────────
def search_flow():
    platform_choices = list(PLATFORMS.keys())
    selected = questionary.checkbox(
        "Select platforms to search:",
        choices=[questionary.Choice(p, checked=True) for p in platform_choices],
        style=QUESTIONARY_STYLE,
    ).ask()
    if not selected:
        console.print("[yellow]No platforms selected.[/]")
        return

    user_input = questionary.text(
        "Describe what you're looking for:",
        style=QUESTIONARY_STYLE,
    ).ask()
    if not user_input:
        return

    console.print()
    q_info = expand_query(user_input)
    console.print(
        f"[dim]Query:[/] [bold]{q_info['en_query']}[/]  "
        f"[dim]Language:[/] {q_info['language']}  "
        f"[dim]Type:[/] {q_info['type']}"
    )
    console.print()

    with Progress(SpinnerColumn(), TextColumn("[cyan]Searching platforms..."), transient=True) as p:
        p.add_task("", total=None)
        results = search_all(q_info, selected)

    if not results:
        console.print("[red]No results found. Try different keywords.[/]")
        return

    results = _prefilter_results(results, q_info.get("keywords", []))

    with Progress(SpinnerColumn(), TextColumn("[cyan]AI ranking results..."), transient=True) as p:
        p.add_task("", total=None)
        results = ai_rank_results(results, user_input)

    console.print(f"[green]Found {len(results)} results[/]\n")
    display_results_table(results)
    console.print()
    handle_result_selection(results, selected)

# ───────────────────────────────────────────────────────────────
# MAIN MENU
# ───────────────────────────────────────────────────────────────
def main():
    print_logo()
    while True:
        choice = questionary.select(
            "Main Menu:",
            choices=[
                "Search for projects",
                "Analyze project by URL",
                "Compare projects",
                "Exit",
            ],
            style=QUESTIONARY_STYLE,
        ).ask()

        if not choice or choice == "Exit":
            console.print("[dim]Goodbye.[/]")
            break
        elif choice == "Search for projects":
            search_flow()
        elif choice == "Analyze project by URL":
            analyze_by_url()
        elif choice == "Compare projects":
            compare_projects()

        console.print()

if __name__ == "__main__":
    main()
