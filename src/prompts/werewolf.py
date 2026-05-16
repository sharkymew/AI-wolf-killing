"""狼人夜晚行动专用 prompt（盲选 + 协商）。"""
from __future__ import annotations
from typing import List


def build_wolf_first_prompt(public_facts: List[str]) -> str:
    """狼人首轮盲选 prompt。"""
    known_info = ""
    if public_facts:
        known_info = "【当前已知信息】\n" + "\n".join(public_facts[-5:]) + "\n"

    advice = (
        f"{known_info}"
        "你可以选择攻击包括自己在内的任何存活玩家。\n"
        "【重要】请根据已知信息做出独立判断。相信自己的分析，选择你认为最应该击杀的目标。\n"
        "注意：自杀（攻击狼人队友）是一种高风险高回报的战术，通常用于骗取女巫解药或混淆视听。\n"
        "请慎重选择，除非有明确战术目的，否则建议优先攻击好人。"
    )
    return f"狼人杀人（第1轮盲选）\n{advice}"


def build_wolf_negotiation_prompt(
    round_idx: int,
    max_rounds: int,
    votes_context: str,
    wolves_count: int,
) -> str:
    """狼人协商阶段 prompt（round_idx 从 0 起计）。"""
    last_round_notice = ""
    if round_idx == max_rounds - 1 and wolves_count > 1:
        last_round_notice = (
            "\n【最后一轮】这轮之后将强制锁定目标。请认真考虑队友的观点，"
            "但最终还是要相信自己的判断。如果你有充分理由坚持自己的目标，可以保持不变。"
        )
    prompt_prefix = (
        f"【协商中】当前协商情况：{votes_context}。\n"
        "请基于已知信息和你的独立判断做出选择。不要盲目跟从队友——"
        "如果你认为自己的目标更有道理，请坚持。批判性地评估每个选项。\n"
        "只有在队友理由充分时才考虑改变你的选择。"
        f"{last_round_notice}"
    )
    return f"狼人杀人（协商第{round_idx + 1}轮）\n{prompt_prefix}"
