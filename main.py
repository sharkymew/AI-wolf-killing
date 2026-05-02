import typer
import webbrowser
from pathlib import Path
from typing import Optional
from src.utils.config import load_config
from src.core.game import GameEngine
from src.utils.logger import game_logger
from dotenv import load_dotenv

def _get_version():
    vf = Path(__file__).parent / "VERSION"
    if vf.exists():
        return vf.read_text().strip()
    return "0.0.0"

def _version_callback(value: bool):
    if value:
        print(f"AI-Werewolf v{_get_version()}")
        raise typer.Exit()

app = typer.Typer()

@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-v", callback=_version_callback, is_eager=True,
                                  help="Show version and exit"),
):
    pass


@app.command()
def start(
    config_path: str = typer.Option("config/game_config.yaml", "--config", "-c", help="Path to configuration file"),
    rounds: Optional[int] = typer.Option(None, "--rounds", "-r", help="Override max game rounds"),
):
    """Start the AI Werewolf Game in terminal mode."""
    load_dotenv()

    try:
        game_logger.log("欢迎来到 AI 狼人杀！", "bold magenta")

        config = load_config(config_path)
        if rounds is not None:
            config.game.max_turns = rounds

        engine = GameEngine(config)
        import asyncio
        asyncio.run(engine.run())

    except Exception as e:
        game_logger.error(f"Game Error: {e}")
        raise e


@app.command()
def server(
    config_path: str = typer.Option("config/game_config.yaml", "--config", "-c", help="Path to configuration file"),
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Server host"),
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser automatically"),
):
    """Start the AI Werewolf Game with Web UI server."""
    load_dotenv()

    try:
        game_logger.log("Starting AI Werewolf Web Server...", "bold magenta")
        game_logger.log(f"Backend: http://{host}:{port}", "green")
        game_logger.log("Frontend: cd frontend && npm run dev", "cyan")

        if not no_browser:
            webbrowser.open(f"http://localhost:{port}")

        import uvicorn
        uvicorn.run(
            "src.server.game_server:app",
            host=host,
            port=port,
            log_level="info",
        )

    except Exception as e:
        game_logger.error(f"Server Error: {e}")
        raise e


if __name__ == "__main__":
    app()
