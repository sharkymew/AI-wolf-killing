"""游戏阶段模块。

phase 函数接收 `GameEngine` 实例作为上下文容器：从中读 `players` /
`public_facts` / `turn`，调用 `engine._emit` / `engine.broadcast` /
`engine.log_event` 等基础设施。phase 之间互相调用直接 import。
"""
