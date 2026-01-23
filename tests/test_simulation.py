import sys
import os
sys.path.append(os.getcwd())

import asyncio
from src.utils.config import load_config
from src.core.game import GameEngine

def test_simulation():
    print("Starting simulation...")
    config = load_config("config/test_config.yaml")
    engine = GameEngine(config)
    asyncio.run(engine.run())
    print("Simulation finished.")

if __name__ == "__main__":
    test_simulation()
