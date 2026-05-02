import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import AsyncMock, MagicMock
from src.core.player import Player
from src.core.role import Villager, Werewolf


def _make_player(mock_response="test speech", is_reasoning=False) -> Player:
    mock_client = MagicMock()
    mock_client.config = MagicMock()
    mock_client.config.is_reasoning = is_reasoning
    mock_client.config.json_mode = False
    mock_client.config.max_memory_tokens = 2000
    mock_client.generate_response = AsyncMock(return_value=mock_response)
    return Player(1, Villager(), mock_client, "mock")


class TestSpeak(unittest.IsolatedAsyncioTestCase):
    async def test_speak_non_reasoning_returns_response(self):
        p = _make_player("我认为3号是狼人。")
        result = await p.speak("讨论", turn=1, alive_count=5)
        self.assertEqual(result, "我认为3号是狼人。")

    async def test_speak_reasoning_uses_two_step(self):
        p = _make_player("我是好人。", is_reasoning=True)
        result = await p.speak("讨论", turn=1, alive_count=5)
        self.assertTrue(len(result) > 0)

    async def test_speak_exception_returns_fallback(self):
        mock_client = MagicMock()
        mock_client.config = MagicMock()
        mock_client.config.is_reasoning = False
        mock_client.config.json_mode = False
        mock_client.config.max_memory_tokens = 2000
        mock_client.generate_response = AsyncMock(side_effect=RuntimeError("API down"))
        p = Player(1, Villager(), mock_client, "mock")
        result = await p.speak("讨论", turn=1, alive_count=3)
        self.assertIn("发言失败", result)

    async def test_speak_with_public_facts(self):
        p = _make_player("我认为2号是狼人。")
        result = await p.speak("讨论", public_facts=["玩家 3 死亡，身份是 狼人"], turn=2)
        self.assertTrue(len(result) > 0)

    async def test_speak_endgame_good(self):
        p = _make_player("果断出1号！", is_reasoning=True)
        result = await p.speak("讨论", is_endgame=True, turn=3, alive_count=3)
        self.assertTrue(len(result) > 0)

    async def test_speak_endgame_wolf(self):
        mock_client = MagicMock()
        mock_client.config = MagicMock()
        mock_client.config.is_reasoning = False
        mock_client.config.json_mode = False
        mock_client.config.max_memory_tokens = 2000
        mock_client.generate_response = AsyncMock(return_value="我是好人，相信我。")
        p = Player(1, Werewolf(), mock_client, "mock")
        result = await p.speak("讨论", is_endgame=True, turn=3, alive_count=3)
        self.assertIn("我是好人", result)


if __name__ == "__main__":
    unittest.main()
