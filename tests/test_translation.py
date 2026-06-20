from utils.translation import detect_language, translate_to_english, translate_text


def test_detect_english():
    assert detect_language("hello world") == "en"
    assert detect_language("") == "en"


def test_detect_arabic():
    assert detect_language("مرحبا بالعالم") == "ar"


def test_detect_japanese():
    assert detect_language("こんにちは") == "ja"
    assert detect_language("コンニチハ") == "ja"


def test_detect_korean():
    assert detect_language("안녕하세요") == "ko"


def test_detect_russian():
    assert detect_language("привет мир") == "ru"


def test_detect_hindi():
    assert detect_language("नमस्ते दुनिया") == "hi"


def test_detect_chinese():
    assert detect_language("你好世界") == "zh"


def test_detect_mixed_latin_non_latin():
    assert detect_language("hello مرحبا") == "ar"


def test_detect_non_latin_precedence():
    assert detect_language("hello こんにちは") == "ja"


def test_translate_to_english_passthrough():
    assert translate_to_english("hello world") == "hello world"
    assert translate_to_english("web scraper") == "web scraper"


def test_translate_to_english_arabic():
    result = translate_to_english("أداة لفحص الشبكات")
    assert result is not None
    assert len(result) > 2
    assert detect_language(result) == "en"


def test_translate_to_english_french():
    result = translate_to_english("outil de compression de fichiers")
    assert result is not None
    assert len(result) > 2
    assert detect_language(result) == "en" or "scanner" in result.lower() or "network" in result.lower()


def test_translate_text_to_arabic():
    result = translate_text("hello world", "ar")
    assert result is not None
    assert len(result) > 0


def test_translate_text_to_french():
    result = translate_text("hello world", "fr")
    assert result is not None
    assert len(result) > 0


def test_detect_empty_string():
    assert detect_language("") == "en"


def test_detect_only_numbers_symbols():
    assert detect_language("12345 !@#$%") == "en"
