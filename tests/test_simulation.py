import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
import yaml
from src.utils.config import load_config
from src.core.game import GameEngine


def _write_config(data):
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True)
    return path


class TestSimulation(unittest.IsolatedAsyncioTestCase):
    async def test_full_game_completes(self):
        config = load_config("config/test_config.yaml")
        engine = GameEngine(config)
        await engine.run()
        self.assertTrue(engine.game_over or engine.turn > config.game.max_turns)
        self.assertIsNotNone(engine.winner)

    async def test_simulation_with_guard(self):
        data = {
            "models": [
                {"name": "A", "provider": "mock", "model": "mock"},
                {"name": "B", "provider": "mock", "model": "mock"},
                {"name": "C", "provider": "mock", "model": "mock"},
                {"name": "D", "provider": "mock", "model": "mock"},
                {"name": "E", "provider": "mock", "model": "mock"},
                {"name": "F", "provider": "mock", "model": "mock"},
                {"name": "G", "provider": "mock", "model": "mock"},
            ],
            "game": {
                "roles": {
                    "werewolf": 2, "witch": 1, "seer": 1,
                    "hunter": 0, "guard": 1, "villager": 2
                },
                "max_turns": 10,
            }
        }
        path = _write_config(data)
        config = load_config(path)
        engine = GameEngine(config)
        await engine.run()
        self.assertTrue(engine.game_over or engine.turn > config.game.max_turns)

    async def test_simulation_with_idiot(self):
        data = {
            "models": [
                {"name": "A", "provider": "mock", "model": "mock"},
                {"name": "B", "provider": "mock", "model": "mock"},
                {"name": "C", "provider": "mock", "model": "mock"},
                {"name": "D", "provider": "mock", "model": "mock"},
                {"name": "E", "provider": "mock", "model": "mock"},
                {"name": "F", "provider": "mock", "model": "mock"},
                {"name": "G", "provider": "mock", "model": "mock"},
            ],
            "game": {
                "roles": {
                    "werewolf": 2, "witch": 1, "seer": 1,
                    "hunter": 1, "idiot": 1, "villager": 1
                },
                "max_turns": 10,
            }
        }
        path = _write_config(data)
        config = load_config(path)
        engine = GameEngine(config)
        await engine.run()
        self.assertTrue(engine.game_over or engine.turn > config.game.max_turns)


if __name__ == "__main__":
    unittest.main()
