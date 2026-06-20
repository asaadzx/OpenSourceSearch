from ai_backend.llm_handler import _is_valid_ai_response, safe_parse_ai_json, ai_chat


def test_is_valid_response_normal():
    assert _is_valid_ai_response("This is a valid response about code.") is True


def test_is_valid_response_too_short():
    assert _is_valid_ai_response("Hi") is False


def test_is_valid_response_empty():
    assert _is_valid_ai_response("") is False
    assert _is_valid_ai_response("   ") is False


def test_is_valid_response_junk_patterns():
    assert _is_valid_ai_response("Sorry, I cannot help with that.") is False
    assert _is_valid_ai_response("I'm not able to answer that question.") is False
    assert _is_valid_ai_response("As an AI, I don't have that information.") is False


def test_safe_parse_json_dict():
    raw = '{"key": "value"}'
    result = safe_parse_ai_json(raw, dict)
    assert result == {"key": "value"}


def test_safe_parse_json_list():
    raw = '[{"id": 1, "score": 50}]'
    result = safe_parse_ai_json(raw, list)
    assert result == [{"id": 1, "score": 50}]


def test_safe_parse_json_with_markdown():
    raw = '```json\n{"hello": "world"}\n```'
    result = safe_parse_ai_json(raw, dict)
    assert result == {"hello": "world"}


def test_safe_parse_json_with_text_wrapping():
    raw = 'Here is the result:\n{"nested": {"inner": true}}\nEnd.'
    result = safe_parse_ai_json(raw, dict)
    assert result == {"nested": {"inner": True}}


def test_safe_parse_json_trailing_comma():
    raw = '{"a": 1, "b": 2,}'
    result = safe_parse_ai_json(raw, dict)
    assert result == {"a": 1, "b": 2}


def test_safe_parse_invalid_wrong_type():
    raw = '{"key": "value"}'
    result = safe_parse_ai_json(raw, list)
    assert result is None


def test_safe_parse_empty():
    assert safe_parse_ai_json("", dict) is None
    assert safe_parse_ai_json(None, dict) is None


def test_safe_parse_garbage():
    assert safe_parse_ai_json("not json at all !!!", dict) is None


def test_safe_parse_nested_brackets_in_string():
    raw = '{"text": "hello {world} [test]"}'
    result = safe_parse_ai_json(raw, dict)
    assert result is not None
    assert result["text"] == "hello {world} [test]"


def test_ai_chat_no_prompt():
    result = ai_chat("")
    assert result == "" or len(result) >= 20
