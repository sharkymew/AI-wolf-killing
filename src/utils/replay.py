"""游戏回放保存。

把对局完整 history + config（API key 已 mask）写入
`logs/json/replay_YYYYMMDD_HHMMSS.json`，方便事后复盘。
"""
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

from src.utils.logger import game_logger

if TYPE_CHECKING:
    from src.core.game import GameEngine


def save_replay(engine: "GameEngine") -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"logs/json/replay_{timestamp}.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    safe_config = engine.config.model_dump()
    for model in safe_config.get("models", []):
        if "api_key" in model:
            model["api_key"] = "***"
    if safe_config.get("judge_model") and "api_key" in safe_config["judge_model"]:
        safe_config["judge_model"]["api_key"] = "***"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            {
                "config": safe_config,
                "history": engine.history,
                "winner": engine.winner,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    game_logger.log(f"游戏回放已保存至: {filename}", "green")
