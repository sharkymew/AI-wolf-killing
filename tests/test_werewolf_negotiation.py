import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import AsyncMock, MagicMock
from src.core.game import GameEngine
from src.core.player import Player
from src.core.role import Werewolf, Villager
from src.utils.config import AppConfig, GameConfig, RoleConfig, ModelConfig


def _make_wolf(player_id: int, mock_response: str) -> Player:
    mock_client = MagicMock()
    mock_client.config = MagicMock()
    mock_client.config.is_reasoning = False
    mock_client.config.json_mode = False
    mock_client.config.max_memory_tokens = 2000
    mock_client.generate_response = AsyncMock(return_value=mock_response)
    return Player(player_id, Werewolf(), mock_client, "mock")


class TestWerewolfNegotiation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        mock_model = ModelConfig(name="mock", provider="mock", model="mock")
        roles = RoleConfig(werewolf=2, villager=3, witch=0, seer=0)
        self.config = AppConfig(
            models=[mock_model] * 5,
            game=GameConfig(roles=roles, max_turns=20),
        )
        self.engine = GameEngine(self.config)

    def _setup_game(self, wolf1_resp, wolf2_resp):
        w1 = _make_wolf(1, wolf1_resp)
        w2 = _make_wolf(2, wolf2_resp)
        self.engine.players = {
            1: w1, 2: w2,
            3: _make_wolf(3, "1"),  # villager placeholder
            4: _make_wolf(4, "1"),
            5: _make_wolf(5, "1"),
        }
        # Set last 3 as alive villagers
        for pid in [3, 4, 5]:
            self.engine.players[pid].role = Villager()
            self.engine.players[pid].is_alive = True

    async def test_wolves_consensus_returns_target(self):
        self._setup_game("3", "3")
        target = await self.engine._werewolf_action()
        self.assertEqual(target, 3)

    async def test_wolves_disagree_enter_negotiation(self):
        self._setup_game("3", "4")
        target = await self.engine._werewolf_action()
        self.assertIsNotNone(target)
        self.assertIn(target, [3, 4])

    async def test_wolves_all_fail_returns_none(self):
        w1 = _make_wolf(1, "not a number")
        w2 = _make_wolf(2, "garbage")
        w1.llm_client.generate_response = AsyncMock(side_effect=RuntimeError("fail"))
        w2.llm_client.generate_response = AsyncMock(side_effect=RuntimeError("fail"))
        self.engine.players = {
            1: w1, 2: w2,
            3: _make_wolf(3, "1"), 4: _make_wolf(4, "1"), 5: _make_wolf(5, "1"),
        }
        for pid in [3, 4, 5]:
            self.engine.players[pid].role = Villager()
            self.engine.players[pid].is_alive = True
        target = await self.engine._werewolf_action()
        self.assertIsNone(target)


if __name__ == "__main__":
    unittest.main()
