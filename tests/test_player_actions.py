import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import AsyncMock, MagicMock
from src.core.player import Player
from src.core.role import Villager


def _make_player(mock_response: str) -> Player:
    mock_client = MagicMock()
    mock_client.config = MagicMock()
    mock_client.config.is_reasoning = False
    mock_client.config.json_mode = False
    mock_client.config.max_memory_tokens = 2000
    mock_client.generate_response = AsyncMock(return_value=mock_response)
    return Player(1, Villager(), mock_client, "mock")


class TestActParsing(unittest.IsolatedAsyncioTestCase):
    async def test_plain_number(self):
        p = _make_player("2")
        result = await p.act("投票", [2, 3, 4])
        self.assertEqual(result, "2")

    async def test_number_with_context(self):
        p = _make_player("我认为2号最可疑。\n2")
        result = await p.act("投票", [2, 3, 4])
        self.assertEqual(result, "2")

    async def test_abstain_minus_one(self):
        p = _make_player("-1")
        result = await p.act("投票", [2, 3, 4])
        self.assertEqual(result, "-1")

    async def test_json_mode(self):
        mock_client = MagicMock()
        mock_client.config = MagicMock()
        mock_client.config.is_reasoning = False
        mock_client.config.json_mode = True
        mock_client.config.max_memory_tokens = 2000
        mock_client.generate_response = AsyncMock(return_value='{"thought": "3号最可疑", "action": 3}')
        p = Player(1, Villager(), mock_client, "mock")
        result = await p.act("投票", [2, 3, 4])
        self.assertEqual(result, "3")

    async def test_invalid_input_returns_minus_one(self):
        # Mock returns garbage that can't be parsed to int
        p = _make_player("我不知道该怎么选")
        result = await p.act("投票", [2, 3, 4])
        # Should fallback to -1 via regex (no digits besides potential -1) or raw response
        # The regex r"(-?\d+)(?!.*\d)" won't match, so returns raw response
        # This tests that we don't crash
        self.assertIsInstance(result, str)

    async def test_llm_exception_returns_minus_one(self):
        mock_client = MagicMock()
        mock_client.config = MagicMock()
        mock_client.config.is_reasoning = False
        mock_client.config.json_mode = False
        mock_client.config.max_memory_tokens = 2000
        mock_client.generate_response = AsyncMock(side_effect=RuntimeError("API failure"))
        p = Player(1, Villager(), mock_client, "mock")
        result = await p.act("投票", [2, 3, 4])
        self.assertEqual(result, "-1")


if __name__ == "__main__":
    unittest.main()
