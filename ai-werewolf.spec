# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

added_files = [
    ("frontend/dist", "frontend/dist"),
    ("config", "config"),
    ("VERSION", "."),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        "src", "src.core", "src.core.game", "src.core.player", "src.core.role",
        "src.llm", "src.llm.client", "src.llm.mock_client", "src.llm.base", "src.llm.prompts",
        "src.utils", "src.utils.config", "src.utils.logger",
        "src.server", "src.server.game_server",
        "uvicorn", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http",
        "uvicorn.protocols.websockets",
        "websockets", "websockets.legacy",
        "fastapi", "starlette", "anyio",
        "pydantic", "pydantic.deprecated",
        "tiktoken", "tiktoken_ext", "tiktoken_ext.openai_public",
        "yaml", "rich", "dotenv", "typer",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AI-Werewolf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="AI-Werewolf.app",
        icon=None,
        bundle_identifier="com.sharkymew.ai-werewolf",
    )
