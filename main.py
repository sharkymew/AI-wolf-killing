import typer
import webbrowser
from typing import Optional
from src.utils.config import load_config
from src.core.game import GameEngine
from src.utils.logger import game_logger
from dotenv import load_dotenv

app = typer.Typer()


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
