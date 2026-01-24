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
        p._manage_memory()
        self.assertTrue(len(p.memory) >= 1)
        self.assertEqual(p.memory[0]["role"], "system")
        self.assertTrue(len(p.memory) <= before_len)


if __name__ == "__main__":
    unittest.main()
