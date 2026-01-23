import asyncio
import time
import json
import random
from datetime import datetime
from typing import List, Dict, Optional, Tuple, cast
from src.utils.config import AppConfig
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
        models = [m for m in self.config.models if not m.disabled]
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

    async def _hunter_action(self, hunter_id: int) -> Optional[int]:
        hunter = self.players[hunter_id]
        alive = self.get_alive_players()
        alive = [p for p in alive if p != hunter_id] # Exclude self
        
        if not alive: return None
        
        try:
            resp = await hunter.act("猎人开枪", alive, self.public_facts)
            target = int(resp)
            if target in alive:
                return target
        except:
            pass
        return None

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

    async def _witch_action(self, night_death_id: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
        witch = next((p for p in self.players.values() if p.role.type == RoleType.WITCH), None)
        if not witch or not witch.is_alive:
            return None, None
            
        game_logger.log("女巫正在行动...", "dim")
        witch_role = cast(Witch, witch.role)
        
        save_target = None
        poison_target = None
        
        # Save?
        if night_death_id and witch_role.has_antidote:
            try:
                # Tell witch who died
                witch.receive_message(f"今晚死的是 {night_death_id} 号玩家。是否使用解药？(回答 'yes' 或 'no')")
                
                # We'll ask to save:
                msg = f"今晚 {night_death_id} 号玩家被杀了。你有一瓶解药。输入 {night_death_id} 使用解药，输入 -1 不使用。"
                resp = await witch.act("女巫解药", [night_death_id, -1])
                if int(resp) == night_death_id:
                    save_target = night_death_id
                    witch_role.has_antidote = False
                    return save_target, None # Cannot use both
            except:
                pass
        
        # Poison?
        if not save_target and witch_role.has_poison:
            alive_ids = self.get_alive_players()
            alive_ids.remove(witch.player_id) # Don't poison self usually
            try:
                resp = await witch.act("女巫毒药", alive_ids + [-1])
                target = int(resp)
                if target in alive_ids:
                    poison_target = target
                    witch_role.has_poison = False
            except:
                pass
                
        return save_target, poison_target

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

    async def run_day_phase(self, dead_ids: List[int]):
        game_logger.log("\n天亮了。", "blue")
        
        # Announcement
        if dead_ids:
            game_logger.log(f"昨晚死亡的玩家是: {dead_ids}", "red")
            for pid in dead_ids:
                self.players[pid].update_status(False)
                self.log_event("player_death", {"player_id": pid, "turn": self.turn})
        else:
            game_logger.log("昨晚是平安夜。", "green")
            
        if self.check_win_condition(): return
        
        # Last words for night deaths (Only Night 1 usually has last words)
        if self.turn == 1:
            for pid in dead_ids:
                p = self.players[pid]
                game_logger.log(f"玩家 {pid} 发表遗言...", "yellow")
                statement = await p.speak(f"你已死亡（首夜）。请发表遗言。", self.public_facts)
                self.broadcast(f"玩家 {pid} (遗言): {statement}")
        else:
            if dead_ids:
                game_logger.log(f"非首夜死亡，无遗言。", "dim")

        # Discussion (Sequential preserved for logic)
        game_logger.log("\n开始自由讨论...", "cyan")
        alive = self.get_alive_players()
        # Simple round robin discussion
        discussion_log = []
        for pid in alive:
            p = self.players[pid]
            # Check if endgame (<= 4 players) to trigger decisive mode
            is_endgame = len(alive) <= 4
            
            statement = await p.speak(
                f"当前存活: {alive}。之前的发言: {discussion_log}", 
                self.public_facts,
                is_endgame=is_endgame
            )
            log_msg = f"玩家 {pid}: {statement}"
            game_logger.log(log_msg)
            self.broadcast(log_msg)
            discussion_log.append(log_msg)
            
        # Voting (Parallelized)
        game_logger.log("\n开始投票...", "cyan")
        votes = {}
        
        async def get_vote(pid):
            p = self.players[pid]
            try:
                # Pass public facts to act
                resp = await p.act("投票", [id for id in alive if id != pid], self.public_facts) 
                vote_target = int(resp)
                if vote_target in alive:
                    return pid, vote_target
            except:
                pass
            return pid, None # Abstain

        tasks = [get_vote(pid) for pid in alive]
        results = await asyncio.gather(*tasks)
        
        for pid, vote_target in results:
            if vote_target is not None:
                votes[pid] = vote_target
                game_logger.log(f"玩家 {pid} 投给了 {vote_target}")
            else:
                game_logger.log(f"玩家 {pid} 弃票")
        
        # Tally
        if not votes:
            game_logger.log("无人投票，平安日。")
            self.log_event("vote_result", {"votes": votes, "out": None})
            # PK Logic: If no one votes (rare), maybe just continue.
            return
            
        vote_counts = {}
        for target in votes.values():
            vote_counts[target] = vote_counts.get(target, 0) + 1
            
        max_votes = max(vote_counts.values())
        candidates = [t for t, c in vote_counts.items() if c == max_votes]
        
        if len(candidates) == 1:
            out_id = candidates[0]
            game_logger.log(f"玩家 {out_id} 被投票处决！", "red")
            self.players[out_id].update_status(False)
            
            # Reveal role
            role_name = self.players[out_id].role.name
            game_logger.log(f"玩家 {out_id} 的身份是: {role_name}", "bold red")
            
            # Add to public facts
            fact = f"【系统公告】第 {self.turn} 天白天，玩家 {out_id} 被投票处决，身份是 {role_name}。"
            self.public_facts.append(fact)
            self.broadcast(fact) # Broadcast to all players' memory
            
            self.log_event("vote_result", {"votes": votes, "out": out_id, "role": role_name})
            
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

            if self.check_win_condition(): return
            
            # Last words
            p = self.players[out_id]
            statement = await p.speak("你被投票处决。请发表遗言。", self.public_facts)
            self.broadcast(f"玩家 {out_id} (遗言): {statement}")
            
        else:
            game_logger.log(f"平票 {candidates}，进入PK发言环节...", "bold yellow")
            self.log_event("vote_result_tie", {"votes": votes, "candidates": candidates})
            
            # PK Round (Sequential)
            pk_log = []
            for cid in candidates:
                p = self.players[cid]
                game_logger.log(f"玩家 {cid} PK发言...", "yellow")
                statement = await p.speak(f"你和其他玩家平票。请进行PK发言，争取大家的支持。", self.public_facts)
                log_msg = f"玩家 {cid} (PK): {statement}"
                self.broadcast(log_msg)
                pk_log.append(log_msg)
                
            game_logger.log("\nPK投票...", "cyan")
            pk_votes = {}
            
            async def get_pk_vote(pid):
                p = self.players[pid]
                try:
                    resp = await p.act(f"PK投票（只能投 {candidates} 或 -1）", candidates, self.public_facts)
                    vote_target = int(resp)
                    if vote_target in candidates:
                        return pid, vote_target
                except:
                    pass
                return pid, None

            tasks = [get_pk_vote(pid) for pid in alive]
            results = await asyncio.gather(*tasks)
            
            for pid, vote_target in results:
                if vote_target is not None:
                    pk_votes[pid] = vote_target
                    game_logger.log(f"玩家 {pid} PK投给了 {vote_target}")
                else:
                    game_logger.log(f"玩家 {pid} 弃票")
                     
            # Tally PK
            if not pk_votes:
                 game_logger.log("PK无人投票，平安日。")
                 return
                 
            pk_counts = {}
            for target in pk_votes.values():
                pk_counts[target] = pk_counts.get(target, 0) + 1
            
            pk_max = max(pk_counts.values())
            pk_final = [t for t, c in pk_counts.items() if c == pk_max]
            
            if len(pk_final) == 1:
                out_id = pk_final[0]
                game_logger.log(f"玩家 {out_id} 在PK中被投票处决！", "red")
                self.players[out_id].update_status(False)
                
                role_name = self.players[out_id].role.name
                game_logger.log(f"玩家 {out_id} 的身份是: {role_name}", "bold red")
                
                fact = f"【系统公告】第 {self.turn} 天白天，玩家 {out_id} 在PK中被投票处决，身份是 {role_name}。"
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
