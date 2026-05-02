import asyncio
import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from src.utils.config import load_config
from src.core.game import GameEngine
from src.utils.logger import game_logger

app = FastAPI(title="AI Werewolf Game")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
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
        config = load_config(config_path)
        engine = GameEngine(config, on_event=game_event_handler)
        await engine.run()
        game_logger.log("Game finished.", "green")
    except Exception as e:
        game_logger.error(f"Game Error: {e}")
        await manager.broadcast("error", {"message": str(e)})
