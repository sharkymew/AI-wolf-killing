"""发言阶段 prompt 构建 + 互动符号解析。

`build_speak_prompt` 把白天/PK/遗言等场景共用的发言提示词模板化，
`parse_interaction` 从模型输出中抽取末尾的 [🌹N] / [🍅N] 互动符号。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import re

from src.core.role import Role, Faction


@dataclass(frozen=True)
class SpeakContext:
    role: Role
    public_facts: List[str] = field(default_factory=list)
    is_endgame: bool = False
    turn: Optional[int] = None
    alive_count: Optional[int] = None
    alive_wolves: Optional[int] = None
    alive_good: Optional[int] = None


def _format_facts(public_facts: List[str]) -> str:
    recent_facts = public_facts[-10:] if len(public_facts) > 10 else public_facts
    facts_str = "\n".join(recent_facts)
    if facts_str:
        return f"【已证实事实（必须遵守）】\n{facts_str}\n"
    return ""


def _format_status(ctx: SpeakContext) -> str:
    status_lines = []
    if ctx.turn is not None:
        status_lines.append(f"第{ctx.turn}天")
    if ctx.alive_count is not None:
        status_lines.append(f"场上还剩{ctx.alive_count}人")
    if not status_lines:
        return ""

    urgency = "相对从容"
    if ctx.alive_count is not None:
        if ctx.alive_count <= 4:
            urgency = "非常紧急"
        elif ctx.alive_count <= 6:
            urgency = "比较紧张"
    status_lines.append(f"局势{urgency}")
    status_str = f"【局势信息】{'，'.join(status_lines)}。\n"

    if (
        ctx.role.faction == Faction.WEREWOLF
        and ctx.alive_wolves is not None
        and ctx.alive_good is not None
    ):
        remaining_good = max(ctx.alive_good - ctx.alive_wolves, 0)
        status_str += f"【狼人情报】再击杀{remaining_good}名好人即可达到人数优势胜利。\n"

    return status_str


def _format_endgame_advice(ctx: SpeakContext) -> str:
    if not ctx.is_endgame:
        return ""
    if ctx.role.faction == Faction.GOOD:
        return '\n【重要战术提示】当前局势紧张（剩余玩家少）。如果你是好人，必须果断站边，不要做"理中客"。一旦某个角色的对立面被系统公告证实为狼人，必须无条件信任该角色的所有历史发言。投错好人就输了！'
    return "\n【重要战术提示】当前局势紧张。如果你是狼人，继续你的伪装，利用好人的犹豫，尝试倒打一耙或混淆视听。"


def build_speak_prompt(ctx: SpeakContext, situation: str) -> str:
    """构建白天发言阶段的 prompt（讨论、遗言、PK 申辩共用）。"""
    facts_str = _format_facts(ctx.public_facts)
    status_str = _format_status(ctx)
    advice = _format_endgame_advice(ctx)

    return (
        f"{facts_str}{status_str}现在是白天讨论阶段。\n"
        f"上下文：{situation}{advice}"
        "请发表你的观点（100字以内）。\n"
        "你可以在发言末尾用 [🌹玩家N] 表示送花（信任某人），或用 [🍅玩家N] 表示扔西红柿（怀疑某人）。每轮最多一次。\n"
        "示例：我认为3号发言有道理，值得信任。 [🌹3]"
    )


_INTERACTION_PATTERN = re.compile(r"\[([\U0001f339\U0001f345])(\d+)\]")
_INTERACTION_TRAIL = re.compile(r"\s*\[[\U0001f339\U0001f345]\d+\]\s*$")


def parse_interaction(speech: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """从发言尾部抽取互动符号。

    返回 (清洗后的发言, 互动描述 dict | None)。
    互动描述格式：{"type": "flower" | "tomato", "target": int}
    """
    match = _INTERACTION_PATTERN.search(speech)
    if not match:
        return speech, None
    emoji = match.group(1)
    target = int(match.group(2))
    inter_type = "flower" if "🌹" in emoji else "tomato"
    cleaned = _INTERACTION_TRAIL.sub("", speech).strip()
    return cleaned, {"type": inter_type, "target": target}
