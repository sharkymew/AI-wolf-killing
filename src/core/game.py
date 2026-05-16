"""兼容模块：旧路径 ``from src.core.game import GameEngine`` 仍可工作。

GameEngine 实现已迁移到 ``src.core.engine``。
新代码请直接 import ``src.core.engine``。
"""
from src.core.engine import GameEngine

__all__ = ["GameEngine"]
