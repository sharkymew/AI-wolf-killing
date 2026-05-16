"""行动阶段 prompt 构建。

行动阶段包括：狼人选目标、女巫救/毒、守卫守护、预言家查验、
白天投票、PK 投票、猎人开枪——共用同一套提示词模板。
"""
from __future__ import annotations
from typing import List


def _format_facts(public_facts: List[str]) -> str:
    recent_facts = public_facts[-10:] if len(public_facts) > 10 else public_facts
    facts_str = "\n".join(recent_facts)
    if facts_str:
        return f"【已证实事实（必须遵守）】\n{facts_str}\n"
    return ""


def build_action_prompt(
    action_type: str,
    options: List[int],
    public_facts: List[str],
    *,
    use_json: bool,
) -> str:
    """构建行动阶段 prompt。

    `use_json` 为 True 时要求模型输出 {"thought":..., "action":...}。
    否则投票阶段额外要求"先说理由再换行输出数字"，其他行动只要数字。
    """
    facts_str = _format_facts(public_facts)
    prompt = (
        f"{facts_str}现在是{action_type}阶段。\n"
        f"可选目标ID：{options}\n"
        "如果不确定或想弃票/不使用技能，请回复 -1。\n"
    )

    if use_json:
        prompt += (
            "【重要】请务必输出严格的 JSON 格式，不要包含Markdown代码块（```json ... ```）。\n"
            "格式如下：\n"
            "{\"thought\": \"你的简短思考过程（100字以内）\", \"action\": 目标ID数字}\n"
            "示例：\n"
            "{\"thought\": \"1号发言划水，且攻击了预言家，非常可疑。\", \"action\": 1}\n"
        )
    elif "投票" in action_type:
        prompt += (
            "【重要】请先简短陈述投票理由（一句话），然后换行输出数字。\n"
            "示例：\n"
            "1号发言太划水，不像好人。\n"
            "1\n"
        )
    else:
        prompt += (
            "【重要】请仅输出一个数字（目标玩家ID或-1），不要包含任何其他文字、标点或解释！\n"
            "示例输出：\n"
            "1\n"
            "-1"
        )

    return prompt
