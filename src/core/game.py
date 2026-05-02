import asyncio
import os
import time
import json
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Callable, Awaitable
from src.utils.config import AppConfig, get_active_models
from src.core.player import Player
from src.core.role import RoleType, Faction, create_roles_from_counts
from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.llm.prompts import PERSONALITIES
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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"logs/json/replay_{timestamp}.json"
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        safe_config = self.config.model_dump()
        for model in safe_config.get("models", []):
            if "api_key" in model:
                model["api_key"] = "***"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "config": safe_config,
                "history": self.history,
                "winner": self.winner
            }, f, indent=2, ensure_ascii=False)
        game_logger.log(f"游戏回放已保存至: {filename}", "green")

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
            if judge_config.provider == "mock":
                judge_client = MockLLMClient(judge_config)
            else:
                judge_client = LLMClient(judge_config)

        personality_keys = list(PERSONALITIES.keys())
        random.shuffle(personality_keys)

        async def on_thinking(pid, text):
            await self._emit("player_thinking", {"player_id": pid, "text": text})

        async def on_token_usage(pid, usage):
            await self._emit("token_usage", {"player_id": pid, **usage})

        player_roles = {}
        for i, role in enumerate(roles):
            player_id = i + 1
            model_config = models[i % len(models)]
            personality = personality_keys[i % len(personality_keys)]

            if model_config.provider == "mock":
                client = MockLLMClient(model_config)
            else:
                client = LLMClient(model_config)

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
        await self._emit("game_init", {"players": players_data})

        while not self.game_over:
            game_logger.log(f"\n=== 第 {self.turn} 天 ===", "bold yellow")
            self.log_event("phase_start", {"phase": "night", "turn": self.turn})
            await self._emit("phase", {"phase": "night", "turn": self.turn})

            dead_at_night = await self.run_night_phase()
            self.log_event("night_result", {"dead": dead_at_night})
            await self._emit("night_result", {"dead": dead_at_night})

            self.log_event("phase_start", {"phase": "day", "turn": self.turn})
            await self._emit("phase", {"phase": "day", "turn": self.turn})
            await self.run_day_phase(dead_at_night)

            self.turn += 1
            if self.turn > self.config.game.max_turns:
                if not self.check_win_condition():
                    game_logger.log("达到最大回合数，游戏平局结束。", "red")
                    self.winner = "Draw"
                break

        game_logger.log(f"\n游戏结束！获胜方：{self.winner}", "bold red reverse")
        self.log_event("game_over", {"winner": self.winner})
        await self._emit("game_over", {"winner": self.winner})
        self.save_replay()

    # ── Night phase ─────────────────────────────────────────────────

    async def run_night_phase(self) -> List[int]:
        game_logger.log("\n天黑请闭眼...", "blue")

        target_id = await self._werewolf_action()
        if target_id:
            await self._emit("night_wolf_kill", {"target": target_id})

        guard_id = await self._guard_action()

        save_id, poison_id = await self._witch_action(target_id)
        await self._emit("night_witch", {"save": save_id, "poison": poison_id})

        await self._seer_action()

        deaths: Dict[int, str] = {}

        if target_id and target_id == guard_id:
            game_logger.log(f"守卫守护了玩家 {target_id}，狼刀无效。", "cyan")
        elif target_id and target_id != save_id:
            deaths[target_id] = "wolf"

        if poison_id:
            deaths[poison_id] = "poison"

        final_dead = []
        for pid, reason in deaths.items():
            final_dead.append(pid)

            p = self.players[pid]
            if p.role.type == RoleType.HUNTER and p.role.can_shoot:
                if reason == "poison":
                    game_logger.log(f"玩家 {pid} (猎人) 被毒死，无法开枪。", "dim")
                    p.role.can_shoot = False
                else:
                    shot_id = await self._trigger_hunter_death(pid, "死亡")
                    if shot_id:
                        final_dead.append(shot_id)

        return list(set(final_dead))

    async def _werewolf_action(self) -> Optional[int]:
        wolves = [p for p in self.players.values() if p.is_alive and p.role.type == RoleType.WEREWOLF]
        if not wolves:
            return None

        game_logger.log("狼人正在行动...", "dim")
        alive_ids = self.get_alive_players()
        valid_targets = [pid for pid in alive_ids]
        if not valid_targets:
            return None

        max_rounds = 3
        votes = {}

        async def ask_wolf(wolf, prompt):
            try:
                resp = await wolf.act(prompt, valid_targets)
                target = int(resp)
                if target in valid_targets:
                    return wolf.player_id, target
                game_logger.log(f"狼人 {wolf.player_id} 选择了无效目标 {target}，已跳过。", "dim")
            except (ValueError, TypeError):
                game_logger.log(f"狼人 {wolf.player_id} 响应解析失败，已跳过。", "dim")
            return wolf.player_id, None

        known_info = ""
        if self.public_facts:
            known_info = "【当前已知信息】\n" + "\n".join(self.public_facts[-5:]) + "\n"

        advice = (
            f"{known_info}"
            "你可以选择攻击包括自己在内的任何存活玩家。\n"
            "【重要】请根据已知信息做出独立判断。相信自己的分析，选择你认为最应该击杀的目标。\n"
            "注意：自杀（攻击狼人队友）是一种高风险高回报的战术，通常用于骗取女巫解药或混淆视听。\n"
            "请慎重选择，除非有明确战术目的，否则建议优先攻击好人。"
        )
        prompt = f"狼人杀人（第1轮盲选）\n{advice}"

        tasks = [ask_wolf(w, prompt) for w in wolves]
        results = await asyncio.gather(*tasks)

        for pid, target in results:
            if target is not None:
                votes[pid] = target
                await self._emit("night_wolf_vote", {"wolf_id": pid, "target": target, "round": 0})

        target_counts = {}
        for t in votes.values():
            target_counts[t] = target_counts.get(t, 0) + 1
        unique_targets = list(target_counts.keys())

        if len(unique_targets) == 1:
            final_target = unique_targets[0]
            game_logger.log(f"狼人达成一致，锁定了目标 {final_target}。", "red")
            return final_target

        game_logger.log(f"狼人意见不统一 {votes}，进入协商...", "yellow")

        for round_idx in range(max_rounds):
            current_round_votes = {}
            for i, wolf in enumerate(wolves):
                other_votes_context = []
                for prev_wolf in wolves[:i]:
                    if prev_wolf.player_id in current_round_votes:
                        other_votes_context.append(f"同伴{prev_wolf.player_id}本轮已改选: {current_round_votes[prev_wolf.player_id]}")

                for next_wolf in wolves[i+1:]:
                    if next_wolf.player_id in votes:
                        other_votes_context.append(f"同伴{next_wolf.player_id}上轮选择: {votes[next_wolf.player_id]}")

                context_str = "; ".join(other_votes_context)
                last_round_notice = ""
                if round_idx == max_rounds - 1 and len(wolves) > 1:
                    last_round_notice = (
                        "\n【最后一轮】这轮之后将强制锁定目标。请认真考虑队友的观点，"
                        "但最终还是要相信自己的判断。如果你有充分理由坚持自己的目标，可以保持不变。"
                    )
                prompt_prefix = (
                    f"【协商中】当前协商情况：{context_str}。\n"
                    "请基于已知信息和你的独立判断做出选择。不要盲目跟从队友——"
                    "如果你认为自己的目标更有道理，请坚持。批判性地评估每个选项。\n"
                    "只有在队友理由充分时才考虑改变你的选择。"
                    f"{last_round_notice}"
                )

                try:
                    resp = await wolf.act(f"狼人杀人（协商第{round_idx+1}轮）\n{prompt_prefix}", valid_targets)
                    target = int(resp)
                    if target in valid_targets:
                        current_round_votes[wolf.player_id] = target
                        await self._emit("night_wolf_vote", {"wolf_id": wolf.player_id, "target": target, "round": round_idx + 1})
                except (ValueError, TypeError):
                    continue

            votes = current_round_votes

            target_counts = {}
            for t in votes.values():
                target_counts[t] = target_counts.get(t, 0) + 1
            unique_targets = list(target_counts.keys())

            if len(unique_targets) == 1:
                final_target = unique_targets[0]
                game_logger.log(f"狼人达成一致，锁定了目标 {final_target}。", "red")
                return final_target

            game_logger.log(f"第{round_idx+1}轮协商后仍未一致: {votes}", "yellow")

        final_votes = list(votes.values())
        if not final_votes:
            return None

        target_counts = {}
        for t in final_votes:
            target_counts[t] = target_counts.get(t, 0) + 1
        max_votes = max(target_counts.values())
        top_targets = [pid for pid, cnt in target_counts.items() if cnt == max_votes]
        target = random.choice(top_targets)
        game_logger.log(f"狼人协商超时，强制锁定多数票目标 {target}。", "red")
        return target

    async def _witch_action(self, target_id: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        witch = next((p for p in self.players.values() if p.role.type == RoleType.WITCH), None)
        if not witch or not witch.is_alive:
            return None, None

        game_logger.log("女巫正在行动...", "dim")
        save_id = None
        poison_id = None
        save_parse_failed = False

        if target_id and witch.role.has_antidote:
            try:
                resp = await witch.act("女巫救人", [target_id])
                if int(resp) == target_id:
                    save_id = target_id
                    witch.role.has_antidote = False
            except (ValueError, TypeError):
                save_parse_failed = True
                game_logger.log("女巫救人响应无法解析，本轮跳过毒人。", "yellow")

        alive_ids = self.get_alive_players()
        if witch.role.has_poison and save_id is None and not save_parse_failed:
            try:
                resp = await witch.act("女巫毒人", alive_ids)
                poison_id = int(resp)
                if poison_id not in alive_ids:
                    poison_id = None
                else:
                    witch.role.has_poison = False
            except (ValueError, TypeError):
                poison_id = None

        await self._emit("night_witch_action", {
            "player_id": witch.player_id,
            "save_id": save_id,
            "poison_id": poison_id,
        })
        return save_id, poison_id

    async def _guard_action(self) -> Optional[int]:
        guard = next((p for p in self.players.values() if p.role.type == RoleType.GUARD), None)
        if not guard or not guard.is_alive:
            return None

        game_logger.log("守卫正在行动...", "dim")
        alive_ids = self.get_alive_players()

        valid_targets = [pid for pid in alive_ids if pid != guard.role.last_protected]
        if not valid_targets:
            valid_targets = alive_ids

        try:
            resp = await guard.act("守卫守护", valid_targets)
            target = int(resp)
            if target in valid_targets:
                guard.role.last_protected = target
                await self._emit("night_guard", {"guard_id": guard.player_id, "target": target})
                await self._emit("night_guard_action", {"player_id": guard.player_id, "target": target})
                return target
        except (ValueError, TypeError):
            pass
        return None

    async def _seer_action(self):
        seer = next((p for p in self.players.values() if p.role.type == RoleType.SEER), None)
        if not seer or not seer.is_alive:
            return

        game_logger.log("预言家正在行动...", "dim")
        alive_ids = self.get_alive_players()
        alive_ids.remove(seer.player_id)

        try:
            resp = await seer.act("预言家查验", alive_ids)
            target_id = int(resp)
            if target_id in alive_ids:
                target_p = self.players[target_id]
                identity = "好人" if target_p.role.faction == Faction.GOOD else "狼人"
                seer.receive_message(f"查验结果：{target_id} 号玩家是 {identity}", is_private=True)
                await self._emit("night_seer", {"target": target_id, "result": identity})
                await self._emit("night_seer_action", {"player_id": seer.player_id, "target": target_id, "result": identity})
        except (ValueError, TypeError):
            pass

    # ── Day phase ───────────────────────────────────────────────────

    async def run_day_phase(self, dead_at_night: List[int]):
        if dead_at_night:
            game_logger.log("\n天亮了。昨晚死亡玩家: " + ", ".join(map(str, dead_at_night)), "red")
            for pid in dead_at_night:
                self.players[pid].update_status(False)
                role_name = self.players[pid].role.name
                game_logger.log(f"玩家 {pid} 的身份是: {role_name}", "bold red")
                await self._emit("player_dead", {"player_id": pid, "role_name": role_name})
                fact = f"【系统公告】玩家 {pid} 死亡，身份是 {role_name}。"
                self.public_facts.append(fact)

            for pid in dead_at_night:
                p = self.players[pid]
                statement = await p.speak(
                    "你被狼人杀死。请发表遗言。",
                    self.public_facts,
                    turn=self.turn,
                    alive_count=len(self.get_alive_players()),
                )
                await self._emit("day_speech", {"player_id": pid, "statement": statement, "type": "last_words"})
                self.broadcast(f"玩家 {pid} (遗言): {statement}")

                if self.check_win_condition():
                    return
        else:
            game_logger.log("\n天亮了。昨晚是平安夜。", "green")

        if await self._run_discussion_round():
            return

        game_logger.log("\n开始投票...", "cyan")
        alive_ids = self.get_alive_players()
        votes = await self._collect_votes(alive_ids, alive_ids, "投票")
        await self._emit("day_vote", {"votes": votes})

        await self._resolve_vote_outcome(votes, alive_ids, is_pk=False)

    async def _run_discussion_round(self) -> bool:
        """Returns True if game ended during discussion."""
        game_logger.log("\n开始自由讨论...", "cyan")
        alive_ids = self.get_alive_players()
        is_endgame = len(alive_ids) <= 4

        alive_wolves = len(
            [p for p in self.players.values() if p.is_alive and p.role.faction == Faction.WEREWOLF]
        )
        alive_good = len(
            [p for p in self.players.values() if p.is_alive and p.role.faction == Faction.GOOD]
        )
        for pid in alive_ids:
            p = self.players[pid]
            statement = await p.speak(
                f"你是玩家 {pid}。请发表你的观点。",
                self.public_facts,
                is_endgame,
                turn=self.turn,
                alive_count=len(alive_ids),
                alive_wolves=alive_wolves,
                alive_good=alive_good,
            )
            interaction = None
            if p.last_interaction:
                interaction = {
                    "from_id": pid,
                    "to_id": p.last_interaction["target"],
                    "type": p.last_interaction["type"],
                }
                await self._emit("player_interaction", interaction)
            await self._emit("day_speech", {"player_id": pid, "statement": statement, "type": "discussion", "interaction": interaction})
            self.broadcast(f"玩家 {pid}: {statement}")

        return self.check_win_condition()

    async def _resolve_vote_outcome(self, votes: Dict[int, int], candidates: List[int], is_pk: bool):
        """Resolve voting outcome. If is_pk, candidates are the PK participants."""
        if not votes:
            if not is_pk:
                game_logger.log("无人投票，平安日。", "green")
            return

        counts = self._count_votes(votes)
        counts = {k: v for k, v in counts.items() if k != -1}

        if not counts:
            if not is_pk:
                game_logger.log("无人投票，平安日。", "green")
            return

        max_votes = max(counts.values())
        top = [pid for pid, cnt in counts.items() if cnt == max_votes]

        if len(top) == 1:
            await self._eliminate_player(
                out_id=top[0],
                votes=votes,
                reason_label="被投票处决" if not is_pk else "被PK投票处决",
                log_event_key="vote_result" if not is_pk else "vote_result_pk",
                emit_execute=not is_pk,
            )
            return

        if is_pk:
            game_logger.log(f"PK再次平票 {top}，无人出局。", "red")
            fact = f"【系统公告】PK投票再次平票（{' 和 '.join(map(str, top))}），无人出局。"
            self.public_facts.append(fact)
            self.broadcast(fact)
            self.log_event("vote_result_pk_tie", {"votes": votes, "out": None})
            await self._emit("vote_result_pk_tie", {"votes": votes, "out": None})
            return

        # Regular tie → PK
        game_logger.log(f"投票平局，进入 PK：{top}", "yellow")
        pk_ids = top
        pk_speeches = []

        alive_wolves = len(
            [p for p in self.players.values() if p.is_alive and p.role.faction == Faction.WEREWOLF]
        )
        alive_good = len(
            [p for p in self.players.values() if p.is_alive and p.role.faction == Faction.GOOD]
        )
        for pid in pk_ids:
            p = self.players[pid]
            statement = await p.speak(
                "你进入PK，请发表遗言/申辩。",
                self.public_facts,
                turn=self.turn,
                alive_count=len(self.get_alive_players()),
                alive_wolves=alive_wolves,
                alive_good=alive_good,
            )
            pk_speeches.append((pid, statement))

        for pid, statement in pk_speeches:
            await self._emit("day_speech", {"player_id": pid, "statement": statement, "type": "pk_speech"})
            self.broadcast(f"玩家 {pid} (PK发言): {statement}")

        alive_ids = self.get_alive_players()
        pk_votes = await self._collect_votes(alive_ids, pk_ids, "PK投票")
        await self._resolve_vote_outcome(pk_votes, pk_ids, is_pk=True)

    async def _eliminate_player(self, out_id: int, votes: dict, reason_label: str, log_event_key: str, emit_execute: bool):
        """Unified elimination handler — handles Idiot reveal, death, last words, and hunter trigger."""
        role_name = self.players[out_id].role.name

        if self.players[out_id].role.type == RoleType.IDIOT and not self.players[out_id].role.is_revealed:
            self.players[out_id].role.is_revealed = True
            game_logger.log(f"玩家 {out_id} 是白痴，亮明身份，留在场上！", "bold yellow")
            fact = f"【系统公告】玩家 {out_id} {reason_label}，但其身份是白痴，亮明身份留在场上。"
            self.public_facts.append(fact)
            self.broadcast(fact)
            self.log_event(log_event_key, {"votes": votes, "out": out_id, "role": role_name, "idiot": True})
            await self._emit("idiot_reveal", {"player_id": out_id, "role_name": role_name})
        else:
            self.players[out_id].update_status(False)
            game_logger.log(f"玩家 {out_id} {reason_label}！", "bold red")
            game_logger.log(f"玩家 {out_id} 的身份是: {role_name}", "bold red")
            await self._emit("player_dead", {"player_id": out_id, "role_name": role_name})
            fact = f"【系统公告】玩家 {out_id} {reason_label}，身份是 {role_name}。"
            self.public_facts.append(fact)
            self.broadcast(fact)
            self.log_event(log_event_key, {"votes": votes, "out": out_id, "role": role_name})

            if emit_execute:
                await self._emit("day_execute", {"player_id": out_id, "role_name": role_name, "type": "vote"})

            p = self.players[out_id]
            statement = await p.speak(
                "你被投票处决。请发表遗言。",
                self.public_facts,
                turn=self.turn,
                alive_count=len(self.get_alive_players()),
            )
            self.broadcast(f"玩家 {out_id} (遗言): {statement}")

            await self._trigger_hunter_death(out_id, reason_label)

    # ── Voting helpers ──────────────────────────────────────────────

    def _count_votes(self, votes: Dict[int, int]) -> Dict[int, int]:
        counts = {}
        for target in votes.values():
            counts[target] = counts.get(target, 0) + 1
        return counts

    async def _collect_votes(self, voters: List[int], candidates: List[int], phase_label: str) -> Dict[int, int]:
        tasks = [self.players[pid].act(phase_label, candidates, self.public_facts) for pid in voters]
        results = await asyncio.gather(*tasks)
        votes: Dict[int, int] = {}
        for pid, resp in zip(voters, results):
            try:
                target_id = int(resp)
                if target_id in candidates:
                    votes[pid] = target_id
                else:
                    votes[pid] = -1
            except (ValueError, TypeError):
                votes[pid] = -1

        for pid, target in votes.items():
            if target == -1:
                game_logger.log(f"玩家 {pid} 弃票", "dim")
            else:
                game_logger.log(f"玩家 {pid} 投给了 {target}", "yellow")
        return votes

    # ── Hunter ──────────────────────────────────────────────────────

    async def _trigger_hunter_death(self, hunter_id: int, death_reason: str) -> Optional[int]:
        hunter = self.players[hunter_id]
        if hunter.role.type != RoleType.HUNTER or not hunter.role.can_shoot:
            return None

        game_logger.log(f"玩家 {hunter_id} (猎人) {death_reason}，触发技能！", "bold red")
        hunter.role.can_shoot = False
        shot_id = await self._hunter_action(hunter_id)
        if shot_id:
            game_logger.log(f"猎人开枪带走了玩家 {shot_id}！", "bold red")
            self.players[shot_id].update_status(False)
            shot_role = self.players[shot_id].role.name
            game_logger.log(f"被带走的玩家 {shot_id} 身份是: {shot_role}", "bold red")
            await self._emit("hunter_shoot", {"hunter_id": hunter_id, "target_id": shot_id})
            await self._emit("player_dead", {"player_id": shot_id, "role_name": shot_role})
            fact = f"【系统公告】猎人 {hunter_id} 开枪带走了玩家 {shot_id} ({shot_role})。"
            self.public_facts.append(fact)
            self.broadcast(fact)
            self.log_event("hunter_shoot", {"hunter": hunter_id, "target": shot_id})
            return shot_id
        return None

    async def _hunter_action(self, hunter_id: int) -> Optional[int]:
        hunter = self.players[hunter_id]
        alive = self.get_alive_players()
        alive = [p for p in alive if p != hunter_id]
        if not alive:
            return None
        try:
            resp = await hunter.act("猎人开枪", alive, self.public_facts)
            target = int(resp)
            if target in alive:
                return target
        except (ValueError, TypeError):
            pass
        return None
