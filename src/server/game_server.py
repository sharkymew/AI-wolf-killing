import asyncio
import json
import os
from pathlib import Path
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from src.utils.config import load_config
from src.core.game import GameEngine
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

app = FastAPI(title="AI Werewolf Game")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def is_allowed_origin(origin: str | None) -> bool:
    return bool(origin and origin in ALLOWED_ORIGINS)


def resolve_server_config_path(config_path: str) -> Path:
    """Resolve a websocket-supplied config path under the trusted config dir."""
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


class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, event_type: str, data: dict):
        message = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        dead = []
        for ws in self.connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


manager = ConnectionManager()
current_game_task = None


async def game_event_handler(event_type: str, data: dict):
    await manager.broadcast(event_type, data)


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
                    await ws.send_text(json.dumps({"type": "error", "data": {"message": "游戏已在运行中"}}, ensure_ascii=False))
                    continue
                config_path = cmd.get("config", "config/game_config.yaml")
                current_game_task = asyncio.create_task(run_game(config_path))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


async def run_game(config_path: str):
    try:
        config = load_config(str(resolve_server_config_path(config_path)))
        engine = GameEngine(config, on_event=game_event_handler)
        await engine.run()
        game_logger.log("Game finished.", "green")
    except Exception as e:
        game_logger.error(f"Game Error: {e}")
        await manager.broadcast("error", {"message": str(e)})
