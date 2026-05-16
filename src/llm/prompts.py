"""兼容模块：旧的 `from src.llm.prompts import ...` 仍可工作。

实际内容已迁移到 `src/prompts/`。请新代码直接 import `src.prompts.*`。
"""
from src.prompts.system import (
    PromptManager,
    COMMON_INSTRUCTIONS,
    ROLE_PROMPTS,
)
from src.prompts.personalities import PERSONALITIES

__all__ = [
    "PromptManager",
    "PERSONALITIES",
    "COMMON_INSTRUCTIONS",
    "ROLE_PROMPTS",
]
