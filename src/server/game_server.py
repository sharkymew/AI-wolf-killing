"""兼容模块：旧的 `from src.server.game_server import app` 仍可工作。

实际内容已迁移到 `src.server.app` / `src.server.connection`。
新代码请直接 import `src.server.app`。
"""
from src.server.app import (
    app,
    resolve_server_config_path,
    is_allowed_origin,
    get_allowed_origins,
    game_event_handler,
    run_game,
    manager,
    ALLOWED_ORIGINS,
    DEFAULT_ALLOWED_ORIGINS,
)
from src.server.connection import ConnectionManager

__all__ = [
    "app",
    "resolve_server_config_path",
    "is_allowed_origin",
    "get_allowed_origins",
    "game_event_handler",
    "run_game",
    "manager",
    "ALLOWED_ORIGINS",
    "DEFAULT_ALLOWED_ORIGINS",
    "ConnectionManager",
]
