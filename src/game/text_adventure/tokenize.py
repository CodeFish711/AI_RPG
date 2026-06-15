"""中文分词 helper — 解决 Phase C Task 4 review 发现的 RAG tokenize 缺陷。

src/core/rag_repository.py 的 _terms() 用 `re.findall(r"[\\w]+", text.lower())`,
把连续中文当成单 token。query 与 stored content 加空格分词后才能 token overlap,
RAG 召回才能工作。ChromaRAGRepository.hashed_text_embedding() 内部也调 _terms()
— 同样缺陷,Phase D 切到 Chroma 不会自动解决。本 helper 适用所有 RAG backend。
"""

from __future__ import annotations

import re

import jieba


def tokenize_chinese(text: str) -> str:
    """对文本做中文分词,英文不动。返回各 token 用空格分隔的字符串。

    示例:
        "魔法需要血液代价" → "魔法 需要 血液 代价"
        "magic requires blood" → "magic requires blood"(英文不变)
        "NPC Alice 施放火球术" → 含 "NPC" / "Alice" / "施放" / "火球" 等 token

    注意:jieba 会把已存在的空格也切成独立 token,join 后会出现多余空格。
    用一个 regex 把连续空白折叠回单空格,保证英文段落不被改写。
    """
    if not text:
        return text
    tokens = jieba.cut(text, cut_all=False)
    joined = " ".join(tokens)
    return re.sub(r"\s+", " ", joined).strip()
