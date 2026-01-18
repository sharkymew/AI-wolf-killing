from rich.console import Console
import logging
import os
from datetime import datetime

class GameLogger:
    def __init__(self):
        self.console = Console()
        
        # Ensure log directories exist
        os.makedirs("logs/text_logs", exist_ok=True)
        os.makedirs("logs/json", exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"logs/text_logs/game_{timestamp}.txt"
        
        # File handler for saving all logs to txt
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt="[%X]"))
        
        # Root logger config (File only, keep console clean)
        logging.basicConfig(
            level="INFO",
            format="%(message)s",
            datefmt="[%X]",
            handlers=[
                file_handler
            ]
        )
        # Suppress httpx and openai logs
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        
        self.logger = logging.getLogger("Game")
        self.logger.propagate = False # Independent from root
        self.logger.addHandler(file_handler)
        self.log_file = log_file

    def log(self, message: str, style: str = "white"):
        self.console.print(f"[{style}]{message}[/{style}]")
        self.logger.info(message)

    def info(self, message: str):
        self.logger.info(message)
    
    def error(self, message: str):
        self.console.print(f"[bold red]Error: {message}[/bold red]")
        self.logger.error(message)

game_logger = GameLogger()
