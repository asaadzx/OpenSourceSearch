import re
import requests
from urllib.parse import quote

from core.config import HEADERS_BROWSER, TIMEOUTS

_ARABIC_RANGE = r'[\u0600-\u06FF]+'
_CJK_RANGE = r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+'
_CYRILLIC_RANGE = r'[\u0400-\u04FF]+'
_DEVANAGARI_RANGE = r'[\u0900-\u097F]+'
_JAPANESE_KANA = r'[\u3040-\u309f\u30a0-\u30ff]+'
_KOREAN_RANGE = r'[\uac00-\ud7af]+'

_NON_LATIN_PATTERNS = [
    ('ar', _ARABIC_RANGE),
    ('ja', _JAPANESE_KANA),
    ('ko', _KOREAN_RANGE),
    ('ru', _CYRILLIC_RANGE),
    ('hi', _DEVANAGARI_RANGE),
    ('zh', _CJK_RANGE),
]


def detect_language(text: str) -> str:
    for lang, pattern in _NON_LATIN_PATTERNS:
        if re.search(pattern, text):
            return lang
    return "en"


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
    try:
        from deep_translator import GoogleTranslator
        r = GoogleTranslator(source="auto", target="en").translate(text)
        if r and r.strip() and detect_language(r.strip()) == "en":
            return r.strip()
    except Exception:
        pass
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
    fallback = _translate_ar_fallback(text)
    if fallback and any(c.isascii() and c.isalpha() for c in fallback):
        return fallback
    return text


def translate_text(text: str, target_lang: str) -> str:
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
    try:
        from deep_translator import GoogleTranslator
        r = GoogleTranslator(source="auto", target=target_lang[:2]).translate(text)
        if r and r.strip():
            return r.strip()
    except Exception:
        pass
    try:
        r = requests.post(
            "https://libretranslate.com/translate",
            json={"q": text[:500], "source": "en", "target": target_lang[:2]},
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUTS["translate"],
        )
        if r.status_code == 200:
            t = r.json().get("translatedText", "")
            if t and t.strip():
                return t.strip()
    except Exception:
        pass
    try:
        from ai_backend.llm_handler import ai_chat
        result = ai_chat(
            f"Translate the following text to {target_lang}. "
            f"Return ONLY the translation, nothing else.\n\n{text}",
            min_len=5,
        )
        if result:
            return result.strip()
    except Exception:
        pass
    return text
