import os
import yaml
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class ModelConfig(BaseModel):
    name: str
    provider: str = "openai"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str
    temperature: float = 0.7
    is_reasoning: bool = False  # 是否为推理模型（支持 CoT）

class RoleConfig(BaseModel):
    werewolf: int = 2
    witch: int = 1
    seer: int = 1
    villager: int = 2

class GameConfig(BaseModel):
    roles: RoleConfig = RoleConfig()
    max_turns: int = 50
    memory_retention_turns: int = 10 # Deprecated: Keep last N turns of memory
    max_memory_tokens: int = 2000 # Max tokens for memory retention (using tiktoken)

class AppConfig(BaseModel):
    models: List[ModelConfig]
    judge_model: Optional[ModelConfig] = None # New Judge Model
    game: GameConfig = GameConfig()

def load_config(config_path: str = "config/game_config.yaml") -> AppConfig:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    # Process environment variables for API keys
    for model in data.get("models", []):
        if model.get("api_key", "").startswith("env:"):
            env_var = model["api_key"].split(":", 1)[1]
            model["api_key"] = os.getenv(env_var)
            
    # Process judge model
    if "judge_model" in data:
        judge = data["judge_model"]
        if judge.get("api_key", "").startswith("env:"):
            env_var = judge["api_key"].split(":", 1)[1]
            judge["api_key"] = os.getenv(env_var)

    return AppConfig(**data)
