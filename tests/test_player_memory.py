import asyncio
import unittest
from src.core.role import Villager
from src.core.player import Player
from src.utils.config import ModelConfig
from src.llm.mock_client import MockLLMClient


class PlayerMemoryTests(unittest.TestCase):
    def test_memory_token_limit_applied(self):
        cfg = ModelConfig(name="Mock", provider="mock", model="mock-model")
        client = MockLLMClient(cfg)
        p = Player(1, Villager(), client, "Mock", None, max_memory_tokens=50)
        for i in range(200):
            p.receive_message(f"消息 {i}")
        before_len = len(p.memory)
        asyncio.run(p._manage_memory())
        self.assertTrue(len(p.memory) >= 1)
        self.assertEqual(p.memory[0]["role"], "system")
        self.assertTrue(len(p.memory) <= before_len)

    def test_memory_keeps_system_prompt(self):
        cfg = ModelConfig(name="Mock", provider="mock", model="mock-model")
        client = MockLLMClient(cfg)
        p = Player(1, Villager(), client, "Mock", None, max_memory_tokens=50)
        for i in range(100):
            p.receive_message(f"消息 {i}")
        asyncio.run(p._manage_memory())
        self.assertEqual(p.memory[0]["role"], "system")

    def test_memory_keeps_private_messages(self):
        cfg = ModelConfig(name="Mock", provider="mock", model="mock-model")
        client = MockLLMClient(cfg)
        p = Player(1, Villager(), client, "Mock", None, max_memory_tokens=100)
        p.receive_message("你的狼人同伴是: [2, 3]", is_private=True)
        for i in range(50):
            p.receive_message(f"公开消息 {i}")
        asyncio.run(p._manage_memory())
        private = [m for m in p.memory if "私密信息" in m.get("content", "")]
        self.assertTrue(len(private) > 0)

    def test_max_tokens_fallback(self):
        cfg = ModelConfig(name="Mock", provider="mock", model="mock-model")
        client = MockLLMClient(cfg)
        p = Player(1, Villager(), client, "Mock", None)
        max_t = p._get_max_tokens()
        self.assertEqual(max_t, 2000)


if __name__ == "__main__":
    unittest.main()
