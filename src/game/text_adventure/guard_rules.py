"""text_adventure 硬性规则 — Guard 看到的"绝对不能做的事"。

Phase D 初版,根据 live smoke 调整。
"""


TEXT_ADVENTURE_GUARD_RULES: list[str] = [
    "不要让已经死亡的角色再次出场或说话",
    "不要让玩家凭空获得物品、能力或属性变化",
    "不要忽略已经记录在 player_state 中的玩家状态(已持有物品 / 已学技能 / 已受伤等)",
    "不要让场景位置跳变,除非 narration 中有明确移动叙事",
    "不要违反 world_law 中已确立的世界法则(如魔法代价、神灵规则)",
]
