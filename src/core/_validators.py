"""Shared validators across core/. Centralizes session_id pattern to avoid drift."""

from __future__ import annotations

import re


# session_id 合法字符:字母数字下划线短横,避免路径穿越与文件名歧义。
#
# 这里给 Pydantic Field(pattern=...) 用。Pydantic 2 走 Rust regex (regex crate),
# 默认 single-line mode 下 ^/$ 严格匹配字符串首尾,不接受 trailing \n,不会被
# bypass。Rust regex 不支持 \Z(uppercase),所以这里就用 ^...$ 即可。
SESSION_ID_PATTERN = r"^[A-Za-z0-9_\-]+$"

# 给 Python re 用。Python re 的 $ 在 default mode 下接受 trailing \n 的 bypass
# (例如 re.match(r"^[a-z]+$", "abc\n") 仍然匹配),必须用 \A...\Z + fullmatch 保险。
# 不复用 SESSION_ID_PATTERN 是因为 Python re 不支持 \z(小写),Rust regex 不支持
# \Z(大写),两个引擎对 end-of-string 锚点不兼容。
_SESSION_ID_RE = re.compile(r"\A[A-Za-z0-9_\-]+\Z")


def validate_session_id(session_id: str) -> None:
    """对外部输入的 session_id 做防御性校验。失败抛 ValueError。"""
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise ValueError(f"invalid session_id: {session_id!r}")


def is_valid_session_id(session_id: str) -> bool:
    """内部不变量校验。返回 bool,用于 assert / raise 由调用方决定。"""
    return _SESSION_ID_RE.fullmatch(session_id) is not None
