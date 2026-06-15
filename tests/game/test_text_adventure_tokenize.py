def test_tokenize_chinese_splits_continuous_chinese_with_spaces():
    """连续中文短语被 jieba 分词,各 token 间加空格。"""
    from game.text_adventure.tokenize import tokenize_chinese

    result = tokenize_chinese("魔法需要血液代价")
    assert " " in result, f"分词后应含空格: {result!r}"
    assert "魔法" in result
    assert "代价" in result


def test_tokenize_english_unchanged():
    """纯英文短语不变(英文自带空格)。"""
    from game.text_adventure.tokenize import tokenize_chinese

    text = "magic requires blood as cost"
    result = tokenize_chinese(text)
    assert result == text


def test_tokenize_mixed_chinese_english():
    """中英混合:中文部分分词,英文部分保留。"""
    from game.text_adventure.tokenize import tokenize_chinese

    text = "NPC Alice 施放火球术"
    result = tokenize_chinese(text)
    assert "NPC" in result or "Alice" in result
    assert "火球" in result or "施放" in result


def test_tokenize_empty_string():
    from game.text_adventure.tokenize import tokenize_chinese

    assert tokenize_chinese("") == ""


def test_tokenize_only_whitespace():
    from game.text_adventure.tokenize import tokenize_chinese

    result = tokenize_chinese("   ")
    assert isinstance(result, str)
