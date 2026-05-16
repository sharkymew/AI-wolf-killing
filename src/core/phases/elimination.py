"""玩家淘汰流程。

把"决定淘汰玩家 X"之后的所有后果（白痴翻牌、死亡公告、遗言、
猎人触发开枪）收敛到一处，避免在多个投票路径上重复 5 次。
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from src.core.role import RoleType
from src.events import types as events
from src.utils.logger import game_logger

if TYPE_CHECKING:
    from src.core.game import GameEngine


async def eliminate_player(
    engine: "GameEngine",
    out_id: int,
    *,
    votes: dict,
    reason_label: str,
    log_event_key: str,
    emit_execute: bool,
) -> None:
    """统一淘汰处理：白痴翻牌 → 死亡 → 遗言 → 猎人开枪。"""
    role_name = engine.players[out_id].role.name

    if engine.players[out_id].role.type == RoleType.IDIOT and not engine.players[out_id].role.is_revealed:
        engine.players[out_id].role.is_revealed = True
        game_logger.log(f"玩家 {out_id} 是白痴，亮明身份，留在场上！", "bold yellow")
        fact = f"【系统公告】玩家 {out_id} {reason_label}，但其身份是白痴，亮明身份留在场上。"
        engine.public_facts.append(fact)
        engine.broadcast(fact)
        engine.log_event(log_event_key, {"votes": votes, "out": out_id, "role": role_name, "idiot": True})
        await engine._emit(events.IDIOT_REVEAL, {"player_id": out_id, "role_name": role_name})
        return

    engine.players[out_id].update_status(False)
    game_logger.log(f"玩家 {out_id} {reason_label}！", "bold red")
    game_logger.log(f"玩家 {out_id} 的身份是: {role_name}", "bold red")
    await engine._emit(events.PLAYER_DEAD, {"player_id": out_id, "role_name": role_name})
    fact = f"【系统公告】玩家 {out_id} {reason_label}，身份是 {role_name}。"
    engine.public_facts.append(fact)
    engine.broadcast(fact)
    engine.log_event(log_event_key, {"votes": votes, "out": out_id, "role": role_name})

    if emit_execute:
        await engine._emit(events.DAY_EXECUTE, {"player_id": out_id, "role_name": role_name, "type": "vote"})

    p = engine.players[out_id]
    statement = await p.speak(
        "你被投票处决。请发表遗言。",
        engine.public_facts,
        turn=engine.turn,
        alive_count=len(engine.get_alive_players()),
    )
    engine.broadcast(f"玩家 {out_id} (遗言): {statement}")

    await trigger_hunter_death(engine, out_id, reason_label)


async def trigger_hunter_death(
    engine: "GameEngine",
    hunter_id: int,
    death_reason: str,
) -> Optional[int]:
    """猎人死亡时触发开枪。已被毒杀或已开枪过的猎人无效。"""
    hunter = engine.players[hunter_id]
    if hunter.role.type != RoleType.HUNTER or not hunter.role.can_shoot:
        return None

    game_logger.log(f"玩家 {hunter_id} (猎人) {death_reason}，触发技能！", "bold red")
    hunter.role.can_shoot = False

    shot_id = await _hunter_action(engine, hunter_id)
    if not shot_id:
        return None

    game_logger.log(f"猎人开枪带走了玩家 {shot_id}！", "bold red")
    engine.players[shot_id].update_status(False)
    shot_role = engine.players[shot_id].role.name
    game_logger.log(f"被带走的玩家 {shot_id} 身份是: {shot_role}", "bold red")
    await engine._emit(events.HUNTER_SHOOT, {"hunter_id": hunter_id, "target_id": shot_id})
    await engine._emit(events.PLAYER_DEAD, {"player_id": shot_id, "role_name": shot_role})
    fact = f"【系统公告】猎人 {hunter_id} 开枪带走了玩家 {shot_id} ({shot_role})。"
    engine.public_facts.append(fact)
    engine.broadcast(fact)
    engine.log_event("hunter_shoot", {"hunter": hunter_id, "target": shot_id})
    return shot_id


async def _hunter_action(engine: "GameEngine", hunter_id: int) -> Optional[int]:
    hunter = engine.players[hunter_id]
    alive = [pid for pid in engine.get_alive_players() if pid != hunter_id]
    if not alive:
        return None
    try:
        resp = await hunter.act("猎人开枪", alive, engine.public_facts)
        target = int(resp)
        if target in alive:
            return target
    except (ValueError, TypeError):
        pass
    return None
