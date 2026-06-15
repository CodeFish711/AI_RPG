"""主入口 — 转发到 game.text_adventure.app.main()。

原 world_init MVP 入口已 Phase D 退役。world_init 工作流降级为
text_adventure 的可选开局插件,留 Phase E 处理 --with-world-init flag。
"""

from game.text_adventure.app import main


if __name__ == "__main__":
    main()
