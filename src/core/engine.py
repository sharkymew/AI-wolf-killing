"""游戏核心引擎：状态持有 + 主循环编排。

``GameEngine`` 持有全体玩家、回合计数、公共事实、历史事件，
通过 ``run()`` 驱动夜晚→白天主循环。每个阶段的具体逻辑
已委托给 ``src.core.phases.*`` 模块。
"""
import random
import time
from typing import List, Dict, Optional, Tuple, Callable, Awaitable

from src.core.player import Player
from src.core.role import RoleType, Faction, create_roles_from_counts
from src.events import types as events
from src.llm.factory import create_llm_client
from src.llm.prompts import PERSONALITIES
from src.utils.config import AppConfig, get_active_models
from src.utils.logger import game_logger


class GameEngine:
    def __init__(self, config: AppConfig, on_event: Optional[Callable[[str, dict], Awaitable[None]]] = None):
        self.config = config
        self.players: Dict[int, Player] = {}
        self.turn = 1
        self.game_over = False
        self.winner = None
        self.history: List[Dict] = []
        self.public_facts: List[str] = []
        self.on_event = on_event

    async def _emit(self, event_type: str, data: dict):
        if self.on_event:
            await self.on_event(event_type, data)

    def log_event(self, event_type: str, data: Dict):
        event = {
            "turn": self.turn,
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        }
        self.history.append(event)

    def save_replay(self):
        from src.utils.replay import save_replay
        save_replay(self)

    def initialize_game(self):
        game_logger.log("正在初始化游戏...", "bold cyan")
        seed = getattr(self.config.game, "random_seed", None)
        if seed is not None:
            random.seed(seed)

        r_config = self.config.game.roles
        role_counts = r_config.model_dump()
        roles, unknown_roles = create_roles_from_counts(role_counts)
        if unknown_roles:
            game_logger.log(f"未识别的角色配置: {unknown_roles}，将跳过。", "yellow")

        random.shuffle(roles)

        models = get_active_models(self.config.models)
        judge_config = self.config.judge_model

        judge_client = None
        if judge_config:
            judge_client = create_llm_client(judge_config)

        personality_keys = list(PERSONALITIES.keys())
        random.shuffle(personality_keys)

        async def on_thinking(pid, text):
            await self._emit(events.PLAYER_THINKING, {"player_id": pid, "text": text})

        async def on_token_usage(pid, usage):
            await self._emit(events.TOKEN_USAGE, {"player_id": pid, **usage})

        player_roles = {}
        for i, role in enumerate(roles):
            player_id = i + 1
            model_config = models[i % len(models)]
            personality = personality_keys[i % len(personality_keys)]

            client = create_llm_client(model_config)

            player = Player(
                player_id,
                role,
                client,
                model_config.name,
                judge_client,
                self.config.game.max_memory_tokens,
                thinking_callback=on_thinking,
                personality=personality,
                token_callback=on_token_usage,
            )
            self.players[player_id] = player
            player_roles[player_id] = role.name
            game_logger.log(f"玩家 {player_id} [{personality}] 分配角色: [bold]{role.name}[/bold] (模型: {model_config.name})", "green")

        self.log_event("init", {"roles": player_roles})

        wolves = [p for p in self.players.values() if p.role.type == RoleType.WEREWOLF]
        wolf_ids = [p.player_id for p in wolves]
        for wolf in wolves:
            others = [wid for wid in wolf_ids if wid != wolf.player_id]
            msg = f"你的狼人同伴是: {others}" if others else "你没有狼人同伴。"
            wolf.receive_message(msg, is_private=True)

    def get_alive_players(self) -> List[int]:
        return [pid for pid, p in self.players.items() if p.is_alive]

    def check_win_condition(self) -> bool:
        alive_wolves = [p for p in self.players.values() if p.is_alive and p.role.faction == Faction.WEREWOLF]
        alive_good = [p for p in self.players.values() if p.is_alive and p.role.faction == Faction.GOOD]

        if not alive_wolves:
            self.winner = "好人阵营"
            self.game_over = True
            return True

        if len(alive_wolves) >= len(alive_good):
            self.winner = "狼人阵营"
            self.game_over = True
            return True

        return False

    def broadcast(self, message: str):
        for p in self.players.values():
            if p.is_alive:
                p.receive_message(message)

    # ── Main game loop ──────────────────────────────────────────────

    async def run(self):
        self.initialize_game()

        players_data = []
        for pid, p in self.players.items():
            players_data.append({
                "id": pid,
                "role_name": p.role.name,
                "role_type": p.role.type.value,
                "faction": p.role.faction.value,
                "model": p.model_name,
                "is_alive": p.is_alive,
                "personality": p.personality,
            })
        await self._emit(events.GAME_INIT, {"players": players_data})

        while not self.game_over:
            game_logger.log(f"\n=== 第 {self.turn} 天 ===", "bold yellow")
            self.log_event("phase_start", {"phase": "night", "turn": self.turn})
            await self._emit(events.PHASE, {"phase": "night", "turn": self.turn})

            dead_at_night = await self.run_night_phase()
            self.log_event("night_result", {"dead": dead_at_night})
            await self._emit(events.NIGHT_RESULT, {"dead": dead_at_night})

            self.log_event("phase_start", {"phase": "day", "turn": self.turn})
            await self._emit(events.PHASE, {"phase": "day", "turn": self.turn})
            await self.run_day_phase(dead_at_night)

            self.turn += 1
            if self.turn > self.config.game.max_turns:
                if not self.check_win_condition():
                    game_logger.log("达到最大回合数，游戏平局结束。", "red")
                    self.winner = "Draw"
                break

        game_logger.log(f"\n游戏结束！获胜方：{self.winner}", "bold red reverse")
        self.log_event("game_over", {"winner": self.winner})
        await self._emit(events.GAME_OVER, {"winner": self.winner})
        self.save_replay()

    # ── Night phase ─────────────────────────────────────────────────

    async def run_night_phase(self) -> List[int]:
        from src.core.phases.night import run_night
        return await run_night(self)

    async def _werewolf_action(self) -> Optional[int]:
        from src.core.phases.night import werewolf_kill
        return await werewolf_kill(self)

    async def _witch_action(self, target_id: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        from src.core.phases.night import witch_action
        return await witch_action(self, target_id)

    async def _guard_action(self) -> Optional[int]:
        from src.core.phases.night import guard_action
        return await guard_action(self)

    async def _seer_action(self):
        from src.core.phases.night import seer_action
        await seer_action(self)

    # ── Day phase ───────────────────────────────────────────────────

    async def run_day_phase(self, dead_at_night: List[int]):
        from src.core.phases.day import run_day
        await run_day(self, dead_at_night)

    async def _run_discussion_round(self) -> bool:
        from src.core.phases.day import discussion_round
        return await discussion_round(self)

    async def _resolve_vote_outcome(self, votes: Dict[int, int], candidates: List[int], is_pk: bool):
        from src.core.phases.day import resolve_vote
        await resolve_vote(self, votes, candidates, is_pk=is_pk)

    # ── Voting helpers ──────────────────────────────────────────────

    def _count_votes(self, votes: Dict[int, int]) -> Dict[int, int]:
        from src.core.phases.voting import count_votes
        return count_votes(votes)

    async def _collect_votes(self, voters: List[int], candidates: List[int], phase_label: str) -> Dict[int, int]:
        from src.core.phases.voting import collect_votes
        return await collect_votes(self, voters, candidates, phase_label)

    async def _eliminate_player(self, out_id: int, votes: dict, reason_label: str, log_event_key: str, emit_execute: bool):
        from src.core.phases.elimination import eliminate_player
        await eliminate_player(self, out_id, votes=votes, reason_label=reason_label,
                               log_event_key=log_event_key, emit_execute=emit_execute)

    # ── Hunter ──────────────────────────────────────────────────────

    async def _trigger_hunter_death(self, hunter_id: int, death_reason: str) -> Optional[int]:
        from src.core.phases.elimination import trigger_hunter_death
        return await trigger_hunter_death(self, hunter_id, death_reason)
