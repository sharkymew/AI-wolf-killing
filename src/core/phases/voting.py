"""投票收集与计票。

`collect_votes` 并行向所有 voters 发起投票决策，结果归一化为
`{voter_id: target_id}`，无法解析的视为弃票（target_id = -1）。
"""
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Dict, List

from src.utils.logger import game_logger

if TYPE_CHECKING:
    from src.core.game import GameEngine


async def collect_votes(
    engine: "GameEngine",
    voters: List[int],
    candidates: List[int],
    phase_label: str,
) -> Dict[int, int]:
    tasks = [
        engine.players[pid].act(phase_label, candidates, engine.public_facts)
        for pid in voters
    ]
    results = await asyncio.gather(*tasks)

    votes: Dict[int, int] = {}
    for pid, resp in zip(voters, results):
        try:
            target_id = int(resp)
            votes[pid] = target_id if target_id in candidates else -1
        except (ValueError, TypeError):
            votes[pid] = -1

    for pid, target in votes.items():
        if target == -1:
            game_logger.log(f"玩家 {pid} 弃票", "dim")
        else:
            game_logger.log(f"玩家 {pid} 投给了 {target}", "yellow")

    return votes


def count_votes(votes: Dict[int, int]) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for target in votes.values():
        counts[target] = counts.get(target, 0) + 1
    return counts
