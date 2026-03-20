import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from unittest.mock import MagicMock
from src.core.game import GameEngine
from src.core.player import Player
from src.core.role import RoleType, Faction, Werewolf, Villager, Seer
from src.utils.config import AppConfig, GameConfig, RoleConfig, ModelConfig


def _make_config(werewolf=2, villager=2, seer=1) -> AppConfig:
    mock_model = ModelConfig(name="mock", provider="mock", model="mock")
    roles = RoleConfig(werewolf=werewolf, witch=0, seer=seer, hunter=0, villager=villager)
    return AppConfig(
        models=[mock_model] * (werewolf + villager + seer),
        game=GameConfig(roles=roles, max_turns=20),
    )


def _make_player(player_id: int, role) -> Player:
    mock_client = MagicMock()
    mock_client.config = MagicMock()
    mock_client.config.is_reasoning = False
    mock_client.config.json_mode = False
    mock_client.config.max_memory_tokens = 2000
    return Player(player_id, role, mock_client, "mock")


class TestCheckWinCondition(unittest.TestCase):
    def setUp(self):
        self.config = _make_config()
        self.engine = GameEngine(self.config)

    def _add_player(self, pid, role, alive=True):
        p = _make_player(pid, role)
        p.is_alive = alive
        self.engine.players[pid] = p

    def test_good_wins_when_no_wolves(self):
        self._add_player(1, Villager())
        self._add_player(2, Villager())
        result = self.engine.check_win_condition()
        self.assertTrue(result)
        self.assertEqual(self.engine.winner, "好人阵营")

    def test_wolves_win_when_equal_or_outnumber_good(self):
        self._add_player(1, Werewolf())
        self._add_player(2, Villager())
        result = self.engine.check_win_condition()
        self.assertTrue(result)
        self.assertEqual(self.engine.winner, "狼人阵营")

    def test_game_continues_when_wolves_minority(self):
        self._add_player(1, Werewolf())
        self._add_player(2, Villager())
        self._add_player(3, Villager())
        result = self.engine.check_win_condition()
        self.assertFalse(result)
        self.assertFalse(self.engine.game_over)
        self.assertIsNone(self.engine.winner)


class TestInitializeGame(unittest.TestCase):
    def setUp(self):
        self.config = _make_config(werewolf=2, villager=2, seer=1)
        self.engine = GameEngine(self.config)

    def test_role_assignment_counts(self):
        self.engine.initialize_game()
        total = len(self.engine.players)
        self.assertEqual(total, 5)
        wolf_count = sum(1 for p in self.engine.players.values() if p.role.type == RoleType.WEREWOLF)
        self.assertEqual(wolf_count, 2)

    def test_wolves_know_each_other(self):
        self.engine.initialize_game()
        wolves = [p for p in self.engine.players.values() if p.role.type == RoleType.WEREWOLF]
        if len(wolves) >= 2:
            wolf_ids = {p.player_id for p in wolves}
            for wolf in wolves:
                private_msgs = [m["content"] for m in wolf.memory if "[私密信息]" in m["content"]]
                teammate_ids = wolf_ids - {wolf.player_id}
                for tid in teammate_ids:
                    self.assertTrue(
                        any(str(tid) in msg for msg in private_msgs),
                        f"狼人 {wolf.player_id} 未收到关于同伴 {tid} 的通知"
                    )

    def test_all_players_have_unique_ids(self):
        self.engine.initialize_game()
        pids = list(self.engine.players.keys())
        self.assertEqual(len(pids), len(set(pids)))


class TestGetAlivePlayers(unittest.TestCase):
    def setUp(self):
        self.config = _make_config()
        self.engine = GameEngine(self.config)

    def test_returns_only_alive(self):
        p1 = _make_player(1, Villager())
        p2 = _make_player(2, Villager())
        p2.is_alive = False
        p3 = _make_player(3, Werewolf())
        self.engine.players = {1: p1, 2: p2, 3: p3}
        alive = self.engine.get_alive_players()
        self.assertIn(1, alive)
        self.assertNotIn(2, alive)
        self.assertIn(3, alive)

    def test_empty_when_all_dead(self):
        p1 = _make_player(1, Villager())
        p1.is_alive = False
        self.engine.players = {1: p1}
        self.assertEqual(self.engine.get_alive_players(), [])


if __name__ == "__main__":
    unittest.main()
