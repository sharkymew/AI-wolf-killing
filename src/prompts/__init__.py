"""LLM Prompt 模块：系统提示 + 动态 prompt 构建。"""
from src.prompts.system import (
    PromptManager,
    COMMON_INSTRUCTIONS,
    ROLE_PROMPTS,
)
from src.prompts.personalities import PERSONALITIES
from src.prompts.speak import SpeakContext, build_speak_prompt, parse_interaction
from src.prompts.action import build_action_prompt
from src.prompts.werewolf import (
    build_wolf_first_prompt,
    build_wolf_negotiation_prompt,
)

__all__ = [
    "PromptManager",
    "PERSONALITIES",
    "COMMON_INSTRUCTIONS",
    "ROLE_PROMPTS",
    "SpeakContext",
    "build_speak_prompt",
    "parse_interaction",
    "build_action_prompt",
    "build_wolf_first_prompt",
    "build_wolf_negotiation_prompt",
]
