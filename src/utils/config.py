import os
import warnings
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
    json_mode: bool = False # 是否强制使用 JSON 模式
    max_retries: int = 3 # API 请求重试次数
    disabled: bool = False # 是否禁用此模型
    timeout: float = 60.0

class RoleConfig(BaseModel):
    werewolf: int = 2
    witch: int = 1
    seer: int = 1
    hunter: int = 0
    guard: int = 0
    idiot: int = 0
    villager: int = 2

class GameConfig(BaseModel):
    roles: RoleConfig = RoleConfig()
    max_turns: int = 50
    max_memory_tokens: int = 2000 # Max tokens for memory retention (using tiktoken)
    random_seed: Optional[int] = None

class AppConfig(BaseModel):
    models: List[ModelConfig]
    judge_model: Optional[ModelConfig] = None # New Judge Model
    game: GameConfig = GameConfig()

def get_active_models(models: List[ModelConfig]) -> List[ModelConfig]:
    return [m for m in models if not m.disabled]

def count_players(roles: RoleConfig) -> int:
    return roles.werewolf + roles.witch + roles.seer + roles.hunter + roles.guard + roles.idiot + roles.villager

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

    missing_model_keys = []
    for model in data.get("models", []):
        if model.get("provider") != "mock" and not model.get("api_key"):
            model["disabled"] = True
            missing_model_keys.append(model.get("name", ""))

    if missing_model_keys:
        warnings.warn(
            "Configuration Warning: Missing api_key for models: "
            + ", ".join(filter(None, missing_model_keys))
            + ". These models have been disabled.",
            stacklevel=2,
        )

    if "judge_model" in data:
        judge = data["judge_model"]
        if judge.get("provider") != "mock" and not judge.get("api_key"):
            warnings.warn(
                "Configuration Warning: Missing api_key for judge_model. Judge model disabled.",
                stacklevel=2,
            )
            data.pop("judge_model", None)

    config = AppConfig(**data)
    
    # Validation logic
    active_models = get_active_models(config.models)
    total_players = count_players(config.game.roles)
    
    if len(active_models) < total_players:
        raise ValueError(
            f"Configuration Error: Not enough enabled models for {total_players} players. "
            f"Active models: {len(active_models)}, Required: {total_players}."
        )
        
    # Auto-disable extra models if needed
    if len(active_models) > total_players:
        extra_count = len(active_models) - total_players
        # Disable the last N enabled models
        disabled_count = 0
        auto_disabled_names = []
        for i in range(len(config.models) - 1, -1, -1):
            if not config.models[i].disabled:
                config.models[i].disabled = True
                auto_disabled_names.append(config.models[i].name)
                disabled_count += 1
                if disabled_count >= extra_count:
                    break
        if auto_disabled_names:
            warnings.warn(
                f"自动禁用了多余的模型（共 {len(auto_disabled_names)} 个）：{auto_disabled_names}。"
                f"如需使用这些模型，请增加对应角色数量。",
                UserWarning,
                stacklevel=2,
            )
                    
    return config
