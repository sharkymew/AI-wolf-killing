import asyncio
import time
import json
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple, cast
from src.utils.config import AppConfig, get_active_models
from src.core.player import Player
from src.core.role import RoleType, Faction, Werewolf, Witch, Seer, Hunter, Villager
from src.llm.client import LLMClient
from src.llm.mock_client import MockLLMClient
from src.utils.logger import game_logger

class GameEngine:
    def __init__(self, config: AppConfig):
        # ... (same as before) ...
        self.config = config
        self.players: Dict[int, Player] = {}
        self.turn = 1
        self.game_over = False
        self.winner = None
        self.history: List[Dict] = []
        self.public_facts: List[str] = []

    # ... (log_event, save_replay, initialize_game, get_alive_players, check_win_condition, broadcast stay same) ...
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
        
        # Create safe config dump (exclude api_key)
        safe_config = self.config.model_dump()
        for model in safe_config.get("models", []):
            if "api_key" in model:
                model["api_key"] = "***"  # Mask API key
                
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "config": safe_config,
                "history": self.history,
                "winner": self.winner
            }, f, indent=2, ensure_ascii=False)
        game_logger.log(f"游戏回放已保存至: {filename}", "green")

    def initialize_game(self):
        """Assign roles and initialize players."""
        game_logger.log("正在初始化游戏...", "bold cyan")
        seed = getattr(self.config.game, "random_seed", None)
        if seed is not None:
            random.seed(seed)
        
        # Create role list
        roles = []
        r_config = self.config.game.roles
        for _ in range(r_config.werewolf): roles.append(Werewolf())
        for _ in range(r_config.witch): roles.append(Witch())
        for _ in range(r_config.seer): roles.append(Seer())
        for _ in range(r_config.hunter): roles.append(Hunter())
        for _ in range(r_config.villager): roles.append(Villager())
        
        random.shuffle(roles)
        
        # Assign players to models (round robin or random)
        models = get_active_models(self.config.models)
        judge_config = self.config.judge_model
        
        # Init Judge Client if config exists
        judge_client = None
        if judge_config:
            if judge_config.provider == "mock":
                 judge_client = MockLLMClient(judge_config)
            else:
                 judge_client = LLMClient(judge_config)
        
        player_roles = {}
        for i, role in enumerate(roles):
            player_id = i + 1
            model_config = models[i % len(models)]
            
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
                self.config.game.max_memory_tokens
            )
            self.players[player_id] = player
            player_roles[player_id] = role.name
            
            game_logger.log(f"玩家 {player_id} 分配角色: [bold]{role.name}[/bold] (模型: {model_config.name})", "green")

        self.log_event("init", {"roles": player_roles})

        # Notify Werewolves of their teammates
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
        
        # Wolf Dominance Rule: If Wolves >= Good, Wolves win immediately
        if len(alive_wolves) >= len(alive_good):
            self.winner = "狼人阵营"
            self.game_over = True
            return True
            
        return False

    def broadcast(self, message: str):
        for p in self.players.values():
            if p.is_alive:
                p.receive_message(message)

    async def run(self):
        self.initialize_game()
        
        while not self.game_over:
            game_logger.log(f"\n=== 第 {self.turn} 天 ===", "bold yellow")
            self.log_event("phase_start", {"phase": "night", "turn": self.turn})
            
            # Night Phase
            dead_at_night = await self.run_night_phase()
            self.log_event("night_result", {"dead": dead_at_night})
            
            # Day Phase
            self.log_event("phase_start", {"phase": "day", "turn": self.turn})
            await self.run_day_phase(dead_at_night)
            
            self.turn += 1
            if self.turn > self.config.game.max_turns:
                game_logger.log("达到最大回合数，游戏平局结束。", "red")
                self.winner = "Draw"
                break

        game_logger.log(f"\n游戏结束！获胜方：{self.winner}", "bold red reverse")
        self.log_event("game_over", {"winner": self.winner})
        self.save_replay()

    async def run_night_phase(self) -> List[int]:
        game_logger.log("\n天黑请闭眼...", "blue")
        
        # 1. Werewolf Action
        target_id = await self._werewolf_action()
        
        # 2. Witch Action
        save_id, poison_id = await self._witch_action(target_id)
        
        # 3. Seer Action
        await self._seer_action()
        
        # Calculate deaths with reasons
        deaths = {} # pid -> reason (wolf/poison)
        
        if target_id and target_id != save_id:
            deaths[target_id] = "wolf"
            
        if poison_id:
            deaths[poison_id] = "poison"
            
        # Process Hunter (if dead)
        final_dead = []
        for pid, reason in deaths.items():
            final_dead.append(pid)
            
            # Check Hunter trigger
            p = self.players[pid]
            if p.role.type == RoleType.HUNTER:
                if reason == "poison":
                    game_logger.log(f"玩家 {pid} (猎人) 被毒死，无法开枪。", "dim")
                else:
                    game_logger.log(f"玩家 {pid} (猎人) 死亡，触发技能！", "bold red")
                    shot_id = await self._hunter_action(pid)
                    if shot_id:
                        game_logger.log(f"猎人开枪带走了玩家 {shot_id}！", "bold red")
                        final_dead.append(shot_id)
                        self.log_event("hunter_shoot", {"hunter": pid, "target": shot_id})

        # Remove duplicates
        return list(set(final_dead))

    async def _werewolf_action(self) -> Optional[int]:
        wolves = [p for p in self.players.values() if p.is_alive and p.role.type == RoleType.WEREWOLF]
        if not wolves:
            return None
            
        game_logger.log("狼人正在行动...", "dim")
        
        alive_ids = self.get_alive_players()
        # Allow self-kill logic
        valid_targets = [pid for pid in alive_ids]
        
        # Determine team info for prompt
        teammates = [w.player_id for w in wolves if w.player_id != wolves[0].player_id] # Just for context if needed
        
        if not valid_targets:
            return None

        # Negotiation Loop
        max_rounds = 3
        votes = {} # Initialize outside loop
        
        # Initial blind vote - Parallelize this?
        # Blind vote is independent, so yes.
        # But we need to map responses back to wolves.

        async def ask_wolf(wolf, prompt):
            try:
                resp = await wolf.act(prompt, valid_targets)
                target = int(resp)
                if target in valid_targets:
                    return wolf.player_id, target
            except:
                pass
            return wolf.player_id, None

        # Add specific advice about self-kill
        advice = (
            "你可以选择攻击包括自己在内的任何存活玩家。\n"
            "注意：自杀（攻击狼人队友）是一种高风险高回报的战术，通常用于骗取女巫解药或混淆视听。\n"
            "请慎重选择，除非有明确战术目的，否则建议优先攻击好人。"
        )
        prompt = f"狼人杀人（第1轮盲选）\n{advice}"
        
        # Run parallel
        tasks = [ask_wolf(w, prompt) for w in wolves]
        results = await asyncio.gather(*tasks)
        
        for pid, target in results:
            if target is not None:
                votes[pid] = target
                
        # Check initial consensus
        target_counts = {}
        for t in votes.values():
            target_counts[t] = target_counts.get(t, 0) + 1
        unique_targets = list(target_counts.keys())
        
        if len(unique_targets) == 1:
            final_target = unique_targets[0]
            game_logger.log(f"狼人达成一致，锁定了目标 {final_target}。", "red")
            return final_target
            
        # If mismatch, enter sequential negotiation (Sequential logic preserved for negotiation)
        game_logger.log(f"狼人意见不统一 {votes}，进入协商...", "yellow")
        
        for round_idx in range(max_rounds):
            # Sequential voting: Wolf 1 votes -> Wolf 2 sees Wolf 1's vote and votes -> Wolf 3 sees all previous...
            current_round_votes = {}
            
            # Decide order: maybe shuffle or keep fixed. Let's keep fixed for stability.
            for i, wolf in enumerate(wolves):
                # Construct context of what others have chosen *in this round so far* or *previous round*
                # To solve "lag", we should let them know the CURRENT state of the negotiation
                
                other_votes_context = []
                # Add votes from this round so far
                for prev_wolf in wolves[:i]:
                    if prev_wolf.player_id in current_round_votes:
                        other_votes_context.append(f"同伴{prev_wolf.player_id}本轮已改选: {current_round_votes[prev_wolf.player_id]}")
                
                # Add votes from previous round (or initial) for those who haven't voted yet in this round
                for next_wolf in wolves[i+1:]:
                    if next_wolf.player_id in votes:
                        other_votes_context.append(f"同伴{next_wolf.player_id}上轮选择: {votes[next_wolf.player_id]}")
                        
                context_str = "; ".join(other_votes_context)
                prompt_prefix = (
                    f"【协商中】当前协商情况：{context_str}。请做出你的选择以达成一致。\n"
                    "提醒：如果你们决定自杀（攻击队友），必须达成一致。请确保这是明智的战术决策。"
                )
                
                try:
                    resp = await wolf.act(f"狼人杀人（协商第{round_idx+1}轮）\n{prompt_prefix}", valid_targets)
                    target = int(resp)
                    if target in valid_targets:
                        current_round_votes[wolf.player_id] = target
                except:
                    continue
            
            # Update main votes with this round's result
            votes = current_round_votes
            
            # Check consensus again
            target_counts = {}
            for t in votes.values():
                target_counts[t] = target_counts.get(t, 0) + 1
            unique_targets = list(target_counts.keys())
            
            if len(unique_targets) == 1:
                final_target = unique_targets[0]
                game_logger.log(f"狼人达成一致，锁定了目标 {final_target}。", "red")
                return final_target
                
            game_logger.log(f"第{round_idx+1}轮协商后仍未一致: {votes}", "yellow")

        # If max rounds reached, take majority or random
        final_votes = list(votes.values())
        if not final_votes:
            return None
            
        target = max(set(final_votes), key=final_votes.count)
        game_logger.log(f"狼人协商超时，强制锁定多数票目标 {target}。", "red")
        return target

    async def _witch_action(self, target_id: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        witch = next((p for p in self.players.values() if p.role.type == RoleType.WITCH), None)
        if not witch or not witch.is_alive:
            return None, None
            
        game_logger.log("女巫正在行动...", "dim")
        save_id = None
        poison_id = None
        
        # Witch can save only if someone is killed
        if target_id:
            try:
                resp = await witch.act("女巫救人", [target_id])
                if int(resp) == target_id:
                    save_id = target_id
            except:
                pass
        
        # Witch can poison someone (only once)
        alive_ids = self.get_alive_players()
        if witch.role.poison_used:
            poison_id = None
        else:
            try:
                resp = await witch.act("女巫毒人", alive_ids)
                poison_id = int(resp)
                if poison_id not in alive_ids:
                    poison_id = None
                else:
                    witch.role.poison_used = True
            except:
                poison_id = None
                
        return save_id, poison_id

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
        except:
            pass

    def _count_votes(self, votes: Dict[int, int]) -> Dict[int, int]:
        counts = {}
        for target in votes.values():
            counts[target] = counts.get(target, 0) + 1
        return counts

    async def run_day_phase(self, dead_at_night: List[int]):
        if dead_at_night:
            game_logger.log("\n天亮了。昨晚死亡玩家: " + ", ".join(map(str, dead_at_night)), "red")
            for pid in dead_at_night:
                self.players[pid].update_status(False)
                role_name = self.players[pid].role.name
                game_logger.log(f"玩家 {pid} 的身份是: {role_name}", "bold red")
                fact = f"【系统公告】玩家 {pid} 死亡，身份是 {role_name}。"
                self.public_facts.append(fact)
            
            # Allow last words
            for pid in dead_at_night:
                p = self.players[pid]
                statement = await p.speak("你被狼人杀死。请发表遗言。", self.public_facts)
                self.broadcast(f"玩家 {pid} (遗言): {statement}")
            
            # Process Hunter if any dead at night (after last words)
            for pid in dead_at_night:
                if self.players[pid].role.type == RoleType.HUNTER:
                    if any(
                        self.players[pid].role.type == RoleType.HUNTER
                        and pid in dead_at_night
                        for pid in dead_at_night
                    ):
                        if pid in dead_at_night:
                            game_logger.log(f"玩家 {pid} (猎人) 死亡，触发技能！", "bold red")
                            shot_id = await self._hunter_action(pid)
                            if shot_id:
                                game_logger.log(f"猎人开枪带走了玩家 {shot_id}！", "bold red")
                                self.players[shot_id].update_status(False)
                                shot_role = self.players[shot_id].role.name
                                game_logger.log(f"被带走的玩家 {shot_id} 身份是: {shot_role}", "bold red")
                                fact = f"【系统公告】猎人 {pid} 开枪带走了玩家 {shot_id} ({shot_role})。"
                                self.public_facts.append(fact)
                                self.broadcast(fact)
                                self.log_event("hunter_shoot", {"hunter": pid, "target": shot_id})
            
            if self.check_win_condition():
                return
        else:
            game_logger.log("\n天亮了。昨晚是平安夜。", "green")

        # Daytime discussion
        game_logger.log("\n开始自由讨论...", "cyan")
        speeches = []
        alive_ids = self.get_alive_players()
        is_endgame = len(alive_ids) <= 4
        
        # Let each alive player speak
        for pid in alive_ids:
            p = self.players[pid]
            statement = await p.speak(
                f"你是玩家 {pid}。请发表你的观点。",
                self.public_facts,
                is_endgame
            )
            speeches.append((pid, statement))
            
        # Broadcast all speeches
        for pid, statement in speeches:
            self.broadcast(f"玩家 {pid}: {statement}")

        if self.check_win_condition():
            return
        
        # Voting phase
        game_logger.log("\n开始投票...", "cyan")
        votes = {}
        alive_ids = self.get_alive_players()
        
        tasks = [self.players[pid].act("投票", alive_ids, self.public_facts) for pid in alive_ids]
        results = await asyncio.gather(*tasks)
        
        for pid, resp in zip(alive_ids, results):
            try:
                target_id = int(resp)
                if target_id in alive_ids:
                    votes[pid] = target_id
                else:
                    votes[pid] = -1
            except:
                votes[pid] = -1

        # Display votes
        for pid, target in votes.items():
            if target == -1:
                game_logger.log(f"玩家 {pid} 弃票", "dim")
            else:
                game_logger.log(f"玩家 {pid} 投给了 {target}", "yellow")

        # Determine out player
        if votes:
            counts = self._count_votes(votes)
            counts = {k: v for k, v in counts.items() if k != -1}
            
            if counts:
                max_votes = max(counts.values())
                top = [pid for pid, cnt in counts.items() if cnt == max_votes]
                
                if len(top) == 1:
                    out_id = top[0]
                    self.players[out_id].update_status(False)
                    game_logger.log(f"玩家 {out_id} 被投票处决！", "bold red")
                    role_name = self.players[out_id].role.name
                    game_logger.log(f"玩家 {out_id} 的身份是: {role_name}", "bold red")
                    fact = f"【系统公告】玩家 {out_id} 被投票处决，身份是 {role_name}。"
                    self.public_facts.append(fact)
                    self.broadcast(fact)
                    self.log_event("vote_result", {"votes": votes, "out": out_id, "role": role_name})
                    
                    p = self.players[out_id]
                    statement = await p.speak("你被投票处决。请发表遗言。", self.public_facts)
                    self.broadcast(f"玩家 {out_id} (遗言): {statement}")

                    # Hunter check
                    if self.players[out_id].role.type == RoleType.HUNTER:
                        game_logger.log(f"玩家 {out_id} (猎人) 被投票处决，触发技能！", "bold red")
                        shot_id = await self._hunter_action(out_id)
                        if shot_id:
                            game_logger.log(f"猎人开枪带走了玩家 {shot_id}！", "bold red")
                            self.players[shot_id].update_status(False)
                            
                            shot_role = self.players[shot_id].role.name
                            game_logger.log(f"被带走的玩家 {shot_id} 身份是: {shot_role}", "bold red")
                            
                            fact = f"【系统公告】猎人 {out_id} 开枪带走了玩家 {shot_id} ({shot_role})。"
                            self.public_facts.append(fact)
                            self.broadcast(fact)
                            self.log_event("hunter_shoot", {"hunter": out_id, "target": shot_id})

                    if self.check_win_condition():
                        return
                else:
                    game_logger.log(f"投票平局，进入 PK：{top}", "yellow")
                    # PK logic here... (same as before)
                    
                    pk_ids = top
                    pk_speeches = []
                    for pid in pk_ids:
                        p = self.players[pid]
                        statement = await p.speak(f"你进入PK，请发表遗言/申辩。", self.public_facts)
                        pk_speeches.append((pid, statement))
                    
                    for pid, statement in pk_speeches:
                        self.broadcast(f"玩家 {pid} (PK发言): {statement}")
                    
                    # PK Voting (only alive players not in PK?) Let's allow all alive players vote
                    pk_votes = {}
                    alive_ids = self.get_alive_players()
                    tasks = [self.players[pid].act("PK投票", pk_ids, self.public_facts) for pid in alive_ids]
                    results = await asyncio.gather(*tasks)
                    for pid, resp in zip(alive_ids, results):
                        try:
                            target_id = int(resp)
                            if target_id in pk_ids:
                                pk_votes[pid] = target_id
                            else:
                                pk_votes[pid] = -1
                        except:
                            pk_votes[pid] = -1
                    
                    pk_counts = self._count_votes(pk_votes)
                    pk_counts = {k: v for k, v in pk_counts.items() if k != -1}
                    
                    if pk_counts:
                        max_votes = max(pk_counts.values())
                        pk_final = [pid for pid, cnt in pk_counts.items() if cnt == max_votes]
                        if len(pk_final) == 1:
                            out_id = pk_final[0]
                            self.players[out_id].update_status(False)
                            game_logger.log(f"玩家 {out_id} 被PK投票处决！", "bold red")
                            role_name = self.players[out_id].role.name
                            game_logger.log(f"玩家 {out_id} 的身份是: {role_name}", "bold red")
                            fact = f"【系统公告】玩家 {out_id} 被PK投票处决，身份是 {role_name}。"
                            self.public_facts.append(fact)
                            self.broadcast(fact)
                            
                            self.log_event("vote_result_pk", {"votes": pk_votes, "out": out_id, "role": role_name})
                            
                            # Last words
                            p = self.players[out_id]
                            statement = await p.speak("你被投票处决。请发表遗言。", self.public_facts)
                            self.broadcast(f"玩家 {out_id} (遗言): {statement}")

                            # Hunter check PK
                            if self.players[out_id].role.type == RoleType.HUNTER:
                                 game_logger.log(f"玩家 {out_id} (猎人) 被投票处决，触发技能！", "bold red")
                                 shot_id = await self._hunter_action(out_id)
                                 if shot_id:
                                     game_logger.log(f"猎人开枪带走了玩家 {shot_id}！", "bold red")
                                     self.players[shot_id].update_status(False)
                                     
                                     shot_role = self.players[shot_id].role.name
                                     game_logger.log(f"被带走的玩家 {shot_id} 身份是: {shot_role}", "bold red")
                                     
                                     fact = f"【系统公告】猎人 {out_id} 开枪带走了玩家 {shot_id} ({shot_role})。"
                                     self.public_facts.append(fact)
                                     self.broadcast(fact)
                                     self.log_event("hunter_shoot", {"hunter": out_id, "target": shot_id})

                            if self.check_win_condition(): return
                        else:
                            game_logger.log(f"PK再次平票 {pk_final}，无人出局。", "red")
                            self.log_event("vote_result_pk_tie", {"votes": pk_votes, "out": None})
            else:
                game_logger.log("无人投票，平安日。", "green")
        else:
            game_logger.log("无人投票，平安日。", "green")

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
        except:
            pass
        return None
