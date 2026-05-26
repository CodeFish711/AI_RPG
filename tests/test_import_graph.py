"""静态校验 core/ 与 game/ 边界。

强制两条铁律:
1. core/* 不能 import game/*(由 ast 解析 import 语句校验)
2. core/* 文件代码区不能出现游戏域英文名词(简单 regex,跳过 docstring 与注释)

已知限制 / Phase A 决策:
- 禁词集只覆盖英文(world_law / character / location / scene / npc 等)。
  core/agents/narrative.py 的 _NARRATIVE_INSTRUCTION 含中文"角色/地点/事件"等
  — re.IGNORECASE 的 \\b 不匹配 CJK 边界,所以不会 trip。Phase A 故意不扩展到
  中文,因为这些 prompt prose 在 Phase B 接 TurnLoop 时会重写,届时同步清理。
- 添加新禁词前,先 grep core/*.py 确认无英文 / 中文匹配,否则本测试会立刻 fail。
"""

import ast
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

# core 不允许出现的游戏域名词(case-insensitive 全词匹配)。
# 不含 "world"(spec 自己有 world_memory / world_init 命名),不含 "memory" 等通用词。
_FORBIDDEN_GAME_TERMS = {
    "world_law",
    "character",
    "location",
    "faction",
    "combat",
    "npc",
    "scene",
    "inventory",
    "quest",
    "spell",
}


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py" and path.stat().st_size == 0:
            continue
        yield path


def test_core_does_not_import_game():
    core_root = SRC_ROOT / "core"
    violations: list[str] = []
    for path in _iter_python_files(core_root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("game.") or alias.name == "game":
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module.startswith("game.") or node.module == "game"):
                    violations.append(f"{path}: from {node.module} import ...")
    assert not violations, "core/* must not import game/*:\n" + "\n".join(violations)


def test_core_files_do_not_mention_game_domain_terms():
    core_root = SRC_ROOT / "core"
    violations: list[str] = []
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in _FORBIDDEN_GAME_TERMS) + r")\b",
        re.IGNORECASE,
    )
    for path in _iter_python_files(core_root):
        source = path.read_text(encoding="utf-8")
        # 简易剥离 docstring(连续三引号块);保留注释外的代码。
        in_doc = False
        for line_num, raw in enumerate(source.splitlines(), 1):
            stripped = raw.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                triple_count = raw.count('"""') + raw.count("'''")
                if triple_count >= 2:
                    pass  # 同行开闭
                else:
                    in_doc = not in_doc
                continue
            if in_doc:
                continue
            if stripped.startswith("#"):
                continue
            match = pattern.search(raw)
            if match:
                violations.append(f"{path}:{line_num}: {match.group(0)!r} in: {raw.strip()}")
    assert not violations, (
        "core/* must not mention game domain terms (use generic 'node' / 'memory' / 'event' / 'agent'):\n"
        + "\n".join(violations)
    )
