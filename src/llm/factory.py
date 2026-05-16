"""LLM 客户端工厂。

将 `provider == "mock"` 分支判断从游戏引擎中抽离，
让 `GameEngine` / `Player` 只依赖 `LLMClientProtocol`。
"""
from src.llm.base import LLMClientProtocol
from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.utils.config import ModelConfig


def create_llm_client(config: ModelConfig) -> LLMClientProtocol:
    """根据 provider 字段返回真实或 mock 客户端。"""
    if config.provider == "mock":
        return MockLLMClient(config)
    return LLMClient(config)
