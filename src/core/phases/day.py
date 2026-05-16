"""白天阶段：遗言公告、自由讨论、投票、PK、淘汰。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from src.core.role import Faction
from src.core.phases.voting import collect_votes, count_votes
from src.core.phases.elimination import eliminate_player
from src.events import types as events
from src.utils.logger import game_logger

if TYPE_CHECKING:
    from src.core.game import GameEngine


async def run_day(engine: "GameEngine", dead_at_night: List[int]) -> None:
    """白天主流程。"""
    if dead_at_night:
        game_logger.log("\n天亮了。昨晚死亡玩家: " + ", ".join(map(str, dead_at_night)), "red")
        for pid in dead_at_night:
            engine.players[pid].update_status(False)
            role_name = engine.players[pid].role.name
            game_logger.log(f"玩家 {pid} 的身份是: {role_name}", "bold red")
            await engine._emit(events.PLAYER_DEAD, {"player_id": pid, "role_name": role_name})
            fact = f"【系统公告】玩家 {pid} 死亡，身份是 {role_name}。"
            engine.public_facts.append(fact)

        for pid in dead_at_night:
            p = engine.players[pid]
            statement = await p.speak(
                "你被狼人杀死。请发表遗言。",
                engine.public_facts,
                turn=engine.turn,
                alive_count=len(engine.get_alive_players()),
            )
            await engine._emit(events.DAY_SPEECH, {"player_id": pid, "statement": statement, "type": "last_words"})
            engine.broadcast(f"玩家 {pid} (遗言): {statement}")

            if engine.check_win_condition():
                return
    else:
        game_logger.log("\n天亮了。昨晚是平安夜。", "green")

    if await discussion_round(engine):
        return

    game_logger.log("\n开始投票...", "cyan")
    alive_ids = engine.get_alive_players()
    votes = await collect_votes(engine, alive_ids, alive_ids, "投票")
    await engine._emit(events.DAY_VOTE, {"votes": votes})

    await resolve_vote(engine, votes, alive_ids, is_pk=False)


async def discussion_round(engine: "GameEngine") -> bool:
    """Returns True if game ended during discussion."""
    game_logger.log("\n开始自由讨论...", "cyan")
    alive_ids = engine.get_alive_players()
    is_endgame = len(alive_ids) <= 4

    alive_wolves = len(
        [p for p in engine.players.values() if p.is_alive and p.role.faction == Faction.WEREWOLF]
    )
    alive_good = len(
        [p for p in engine.players.values() if p.is_alive and p.role.faction == Faction.GOOD]
    )
    for pid in alive_ids:
        p = engine.players[pid]
        statement = await p.speak(
            f"你是玩家 {pid}。请发表你的观点。",
            engine.public_facts,
            is_endgame,
            turn=engine.turn,
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
            await engine._emit(events.PLAYER_INTERACTION, interaction)
        await engine._emit(events.DAY_SPEECH, {
            "player_id": pid, "statement": statement,
            "type": "discussion", "interaction": interaction,
        })
        engine.broadcast(f"玩家 {pid}: {statement}")

    return engine.check_win_condition()


async def resolve_vote(
    engine: "GameEngine",
    votes: Dict[int, int],
    candidates: List[int],
    *,
    is_pk: bool,
) -> None:
    """解析投票结果，平票时进入 PK。"""
    if not votes:
        if not is_pk:
            game_logger.log("无人投票，平安日。", "green")
        return

    counts = count_votes(votes)
    counts = {k: v for k, v in counts.items() if k != -1}

    if not counts:
        if not is_pk:
            game_logger.log("无人投票，平安日。", "green")
        return

    max_votes = max(counts.values())
    top = [pid for pid, cnt in counts.items() if cnt == max_votes]

    if len(top) == 1:
        await eliminate_player(
            engine,
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
        engine.public_facts.append(fact)
        engine.broadcast(fact)
        engine.log_event("vote_result_pk_tie", {"votes": votes, "out": None})
        await engine._emit(events.VOTE_RESULT_PK_TIE, {"votes": votes, "out": None})
        return

    # Regular tie → PK
    game_logger.log(f"投票平局，进入 PK：{top}", "yellow")
    pk_ids = top
    pk_speeches = []

    alive_wolves = len(
        [p for p in engine.players.values() if p.is_alive and p.role.faction == Faction.WEREWOLF]
    )
    alive_good = len(
        [p for p in engine.players.values() if p.is_alive and p.role.faction == Faction.GOOD]
    )
    for pid in pk_ids:
        p = engine.players[pid]
        statement = await p.speak(
            "你进入PK，请发表遗言/申辩。",
            engine.public_facts,
            turn=engine.turn,
            alive_count=len(engine.get_alive_players()),
            alive_wolves=alive_wolves,
            alive_good=alive_good,
        )
        pk_speeches.append((pid, statement))

    for pid, statement in pk_speeches:
        await engine._emit(events.DAY_SPEECH, {"player_id": pid, "statement": statement, "type": "pk_speech"})
        engine.broadcast(f"玩家 {pid} (PK发言): {statement}")

    alive_ids = engine.get_alive_players()
    pk_votes = await collect_votes(engine, alive_ids, pk_ids, "PK投票")
    await resolve_vote(engine, pk_votes, pk_ids, is_pk=True)
