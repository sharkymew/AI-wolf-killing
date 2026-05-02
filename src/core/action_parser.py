import re
import json
from typing import List, Optional
from src.utils.logger import game_logger


class ActionParser:
    def __init__(self, judge_client=None):
        self.judge_client = judge_client

    async def parse(
        self,
        response: str,
        options: List[int],
        action_type: str,
        player_id: int,
        use_json: bool = False,
        llm_client=None,
        on_thinking=None,
    ) -> str:
        options_with_abstain = options + [-1]

        def validate(value: str) -> Optional[str]:
            try:
                v = int(value)
            except (TypeError, ValueError):
                return None
            if v in options_with_abstain:
                return str(v)
            return None

        # Tier 1: JSON mode parsing
        if use_json:
            try:
                cleaned = response.replace("```json", "").replace("```", "").strip()
                data = json.loads(cleaned)
                thought = data.get("thought", "")
                action = data.get("action", -1)
                if thought:
                    game_logger.log(f"[dim]玩家 {player_id} 思考: {thought}[/dim]")
                    if on_thinking:
                        await on_thinking(player_id, thought)
                validated = validate(str(action))
                if validated is not None:
                    return validated
            except json.JSONDecodeError:
                game_logger.log(f"JSON解析失败，尝试回退到Regex: {response}", "yellow")

        # Tier 2: Judge model extraction
        if self.judge_client:
            judge_prompt = (
                f"你是一个公正的裁判。\n"
                f"玩家的原始回复是：\n'''{response}'''\n\n"
                f"当前的可选目标ID列表是：{options_with_abstain}（-1表示弃票/跳过）。\n"
                f"请从玩家回复中提取出他最终选择的一个目标ID数字。\n"
                f"注意：\n"
                f"1. 忽略玩家的推理过程，只关注最终选择。\n"
                f"2. 如果玩家回复中包含多个数字，请根据语境判断哪个是最终投票对象。\n"
                f"3. 仅输出一个数字，不要包含任何其他内容。\n"
            )
            try:
                judge_resp = await self.judge_client.generate_response([{"role": "user", "content": judge_prompt}])
                judge_val = judge_resp.strip()
                match = re.search(r"(-?\d+)", judge_val)
                if match:
                    extracted = match.group(1)
                    validated = validate(extracted)
                    if validated is not None:
                        if extracted != response.strip():
                            game_logger.log(f"[dim]裁判判定: 从 '{response}' 提取出 '{extracted}'[/dim]")
                        return validated
            except Exception as e:
                game_logger.log(f"[dim]裁判判决失败: {e}，回退到正则提取[/dim]")

        # Tier 3: Regex fallback
        try:
            match = re.search(r"(-?\d+)(?!.*\d)", response)
            if match:
                extracted = match.group(1)
                validated = validate(extracted)
                if validated is not None:
                    if not self.judge_client and extracted != response:
                        game_logger.log(f"[dim]系统自动修正: 从 '{response}' 提取出 '{extracted}'[/dim]")
                    return validated
        except Exception:
            pass

        # Tier 4: Default
        game_logger.log(
            f"[dim]玩家 {player_id} 无法解析 {action_type} 行为，默认弃票/跳过 (-1)。[/dim]"
        )
        return "-1"
