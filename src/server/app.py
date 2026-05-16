"""FastAPI 应用与 WebSocket 入口。

职责：
- 校验 origin（防 CSWSH）
- 校验请求中的 config 路径，限制只能读 `config/` 目录下的 yaml
- 通过 `ConnectionManager` 广播 `GameEngine` 的事件流到前端
"""
import asyncio
import json
import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.core.game import GameEngine
from src.events import types as events
from src.server.connection import ConnectionManager
from src.utils.config import load_config
from src.utils.logger import game_logger


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


def get_allowed_origins() -> List[str]:
    raw = os.getenv("AI_WEREWOLF_ALLOWED_ORIGINS")
    if not raw:
        return DEFAULT_ALLOWED_ORIGINS
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


ALLOWED_ORIGINS = get_allowed_origins()


def is_allowed_origin(origin: str | None) -> bool:
    return bool(origin and origin in ALLOWED_ORIGINS)


def resolve_server_config_path(config_path: str) -> Path:
    """把 WebSocket 客户端传入的配置路径限制在项目 `config/` 目录下。"""
    requested = Path(config_path)
    if requested.is_absolute():
        raise ValueError("Config path must be relative to the project config directory.")

    if requested.parts and requested.parts[0] == "config":
        requested = Path(*requested.parts[1:])

    resolved = (CONFIG_DIR / requested).resolve()
    if CONFIG_DIR.resolve() not in (resolved, *resolved.parents):
        raise ValueError("Config path escapes the project config directory.")

    if resolved.suffix not in {".yaml", ".yml"}:
        raise ValueError("Config file must be a YAML file.")

    return resolved


app = FastAPI(title="AI Werewolf Game")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


manager = ConnectionManager()
current_game_task: asyncio.Task | None = None


async def game_event_handler(event_type: str, data: dict):
    await manager.broadcast(event_type, data)


async def run_game(config_path: str):
    try:
        config = load_config(str(resolve_server_config_path(config_path)))
        engine = GameEngine(config, on_event=game_event_handler)
        await engine.run()
        game_logger.log("Game finished.", "green")
    except Exception as e:
        game_logger.error(f"Game Error: {e}")
        await manager.broadcast(events.ERROR, {"message": str(e)})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global current_game_task
    if not is_allowed_origin(ws.headers.get("origin")):
        await ws.close(code=1008)
        return

    await manager.connect(ws)
    try:
        while True:
            msg = await ws.receive_text()
            cmd = json.loads(msg)
            if cmd.get("action") == "start":
                if current_game_task and not current_game_task.done():
                    await ws.send_text(
                        json.dumps(
                            {"type": events.ERROR, "data": {"message": "游戏已在运行中"}},
                            ensure_ascii=False,
                        )
                    )
                    continue
                config_path = cmd.get("config", "config/game_config.yaml")
                current_game_task = asyncio.create_task(run_game(config_path))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)
