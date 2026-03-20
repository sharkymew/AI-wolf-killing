import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest
from src.utils.config import load_config
from src.core.game import GameEngine


class TestSimulation(unittest.IsolatedAsyncioTestCase):
    async def test_full_game_completes(self):
        config = load_config("config/test_config.yaml")
        engine = GameEngine(config)
        await engine.run()
        self.assertTrue(engine.game_over or engine.turn > config.game.max_turns)
        self.assertIsNotNone(engine.winner)


if __name__ == "__main__":
    unittest.main()
