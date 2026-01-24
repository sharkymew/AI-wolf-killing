import typer
from typing import Optional
from src.utils.config import load_config
from src.core.game import GameEngine
from src.utils.logger import game_logger
from dotenv import load_dotenv

app = typer.Typer()

@app.command()
def start(
    config_path: str = typer.Option("config/game_config.yaml", "--config", "-c", help="Path to configuration file"),
    rounds: Optional[int] = typer.Option(None, "--rounds", "-r", help="Override max game rounds")
):
    """
    Start the AI Werewolf Game.
    """
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

if __name__ == "__main__":
    app()
