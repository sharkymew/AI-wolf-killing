"""夜晚阶段：每个神职 / 狼人依次行动，汇总死亡名单。"""
from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from src.core.role import RoleType, Faction
from src.events import types as events
from src.prompts.werewolf import build_wolf_first_prompt, build_wolf_negotiation_prompt
from src.utils.logger import game_logger

if TYPE_CHECKING:
    from src.core.game import GameEngine


async def run_night(engine: "GameEngine") -> List[int]:
    """夜晚主流程：狼刀 → 守卫 → 女巫 → 预言家 → 结算死亡。"""
    game_logger.log("\n天黑请闭眼...", "blue")

    target_id = await werewolf_kill(engine)
    if target_id:
        await engine._emit(events.NIGHT_WOLF_KILL, {"target": target_id})

    guard_id = await guard_action(engine)

    save_id, poison_id = await witch_action(engine, target_id)
    await engine._emit(events.NIGHT_WITCH, {"save": save_id, "poison": poison_id})

    await seer_action(engine)

    deaths: Dict[int, str] = {}

    if target_id and target_id == guard_id:
        game_logger.log(f"守卫守护了玩家 {target_id}，狼刀无效。", "cyan")
    elif target_id and target_id != save_id:
        deaths[target_id] = "wolf"

    if poison_id:
        deaths[poison_id] = "poison"

    from src.core.phases.elimination import trigger_hunter_death

    final_dead = []
    for pid, reason in deaths.items():
        final_dead.append(pid)

        p = engine.players[pid]
        if p.role.type == RoleType.HUNTER and p.role.can_shoot:
            if reason == "poison":
                game_logger.log(f"玩家 {pid} (猎人) 被毒死，无法开枪。", "dim")
                p.role.can_shoot = False
            else:
                shot_id = await trigger_hunter_death(engine, pid, "死亡")
                if shot_id:
                    final_dead.append(shot_id)

    return list(set(final_dead))


async def werewolf_kill(engine: "GameEngine") -> Optional[int]:
    """狼人选目标：首轮盲选并发，分歧则最多 3 轮顺序协商。"""
    wolves = [p for p in engine.players.values() if p.is_alive and p.role.type == RoleType.WEREWOLF]
    if not wolves:
        return None

    game_logger.log("狼人正在行动...", "dim")
    valid_targets = engine.get_alive_players()
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

    prompt = build_wolf_first_prompt(engine.public_facts)
    tasks = [ask_wolf(w, prompt) for w in wolves]
    results = await asyncio.gather(*tasks)

    for pid, target in results:
        if target is not None:
            votes[pid] = target
            await engine._emit(events.NIGHT_WOLF_VOTE, {"wolf_id": pid, "target": target, "round": 0})

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
                    other_votes_context.append(
                        f"同伴{prev_wolf.player_id}本轮已改选: {current_round_votes[prev_wolf.player_id]}"
                    )
            for next_wolf in wolves[i + 1:]:
                if next_wolf.player_id in votes:
                    other_votes_context.append(
                        f"同伴{next_wolf.player_id}上轮选择: {votes[next_wolf.player_id]}"
                    )

            context_str = "; ".join(other_votes_context)
            prompt = build_wolf_negotiation_prompt(
                round_idx=round_idx,
                max_rounds=max_rounds,
                votes_context=context_str,
                wolves_count=len(wolves),
            )
            try:
                resp = await wolf.act(prompt, valid_targets)
                target = int(resp)
                if target in valid_targets:
                    current_round_votes[wolf.player_id] = target
                    await engine._emit(events.NIGHT_WOLF_VOTE,
                                       {"wolf_id": wolf.player_id, "target": target, "round": round_idx + 1})
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

        game_logger.log(f"第{round_idx + 1}轮协商后仍未一致: {votes}", "yellow")

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


async def witch_action(
    engine: "GameEngine",
    wolf_target: Optional[int],
) -> Tuple[Optional[int], Optional[int]]:
    """女巫使用解药 / 毒药。"""
    witch = next((p for p in engine.players.values() if p.role.type == RoleType.WITCH), None)
    if not witch or not witch.is_alive:
        return None, None

    game_logger.log("女巫正在行动...", "dim")
    save_id: Optional[int] = None
    poison_id: Optional[int] = None
    save_parse_failed = False

    if wolf_target and witch.role.has_antidote:
        try:
            resp = await witch.act("女巫救人", [wolf_target])
            if int(resp) == wolf_target:
                save_id = wolf_target
                witch.role.has_antidote = False
        except (ValueError, TypeError):
            save_parse_failed = True
            game_logger.log("女巫救人响应无法解析，本轮跳过毒人。", "yellow")

    alive_ids = engine.get_alive_players()
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

    await engine._emit(events.NIGHT_WITCH_ACTION, {
        "player_id": witch.player_id,
        "save_id": save_id,
        "poison_id": poison_id,
    })
    return save_id, poison_id


async def guard_action(engine: "GameEngine") -> Optional[int]:
    """守卫守护一名玩家（不能连守同一人）。"""
    guard = next((p for p in engine.players.values() if p.role.type == RoleType.GUARD), None)
    if not guard or not guard.is_alive:
        return None

    game_logger.log("守卫正在行动...", "dim")
    alive_ids = engine.get_alive_players()

    valid_targets = [pid for pid in alive_ids if pid != guard.role.last_protected]
    if not valid_targets:
        valid_targets = alive_ids

    try:
        resp = await guard.act("守卫守护", valid_targets)
        target = int(resp)
        if target in valid_targets:
            guard.role.last_protected = target
            await engine._emit(events.NIGHT_GUARD, {"guard_id": guard.player_id, "target": target})
            await engine._emit(events.NIGHT_GUARD_ACTION, {"player_id": guard.player_id, "target": target})
            return target
    except (ValueError, TypeError):
        pass
    return None


async def seer_action(engine: "GameEngine") -> None:
    """预言家查验一名玩家身份。"""
    seer = next((p for p in engine.players.values() if p.role.type == RoleType.SEER), None)
    if not seer or not seer.is_alive:
        return

    game_logger.log("预言家正在行动...", "dim")
    alive_ids = engine.get_alive_players()
    alive_ids.remove(seer.player_id)

    try:
        resp = await seer.act("预言家查验", alive_ids)
        target_id = int(resp)
        if target_id in alive_ids:
            target_p = engine.players[target_id]
            identity = "好人" if target_p.role.faction == Faction.GOOD else "狼人"
            seer.receive_message(f"查验结果：{target_id} 号玩家是 {identity}", is_private=True)
            await engine._emit(events.NIGHT_SEER, {"target": target_id, "result": identity})
            await engine._emit(events.NIGHT_SEER_ACTION,
                               {"player_id": seer.player_id, "target": target_id, "result": identity})
    except (ValueError, TypeError):
        pass
