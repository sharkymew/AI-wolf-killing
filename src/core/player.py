from typing import List, Dict, Optional, Callable, Awaitable
from src.core.role import Role, RoleType, Faction
from src.llm.base import LLMClientProtocol
from src.llm.prompts import PromptManager
from src.core.memory import MemoryManager
from src.core.action_parser import ActionParser
from rich.live import Live
from rich.text import Text
from src.utils.logger import game_logger
import re
import json


class Player:
    def __init__(
        self,
        player_id: int,
        role: Role,
        llm_client: LLMClientProtocol,
        model_name: str,
        judge_client: Optional[LLMClientProtocol] = None,
        max_memory_tokens: Optional[int] = None,
        thinking_callback: Optional[Callable[[int, str], Awaitable[None]]] = None,
        personality: str = "",
        token_callback: Optional[Callable[[int, dict], Awaitable[None]]] = None,
    ):
        self.player_id = player_id
        self.role = role
        self.llm_client = llm_client
        self.model_name = model_name
        self.judge_client = judge_client
        self.is_alive = True
        self.memory: List[Dict[str, str]] = []
        self.max_memory_tokens = max_memory_tokens
        self.thinking_callback = thinking_callback
        self.personality = personality
        self.token_callback = token_callback
        self.total_tokens_used = 0
        self.last_interaction = None

        self._init_memory()
        self.memory_mgr = MemoryManager(self.memory, max_memory_tokens, llm_client, player_id)
        self.action_parser = ActionParser(judge_client)

    @property
    def compressions(self):
        return self.memory_mgr.compressions

    @compressions.setter
    def compressions(self, value):
        self.memory_mgr.compressions = value

    def _init_memory(self):
        system_prompt = PromptManager.get_system_prompt(self.role.type, self.player_id, self.personality)
        self.memory.append({"role": "system", "content": system_prompt})

    def receive_message(self, message: str, is_private: bool = False):
        prefix = "[系统通知] " if not is_private else "[私密信息] "
        self.memory.append({"role": "user", "content": f"{prefix}{message}"})

    def _get_current_tokens(self):
        return self.memory_mgr.count_tokens()

    def _get_max_tokens(self):
        return self.memory_mgr.get_max_tokens()

    async def _emit_token_usage(self, last_call: int = 0):
        if self.token_callback:
            max_tokens = self._get_max_tokens()
            current = self._get_current_tokens()
            await self.token_callback(self.player_id, {
                "current_tokens": current,
                "max_tokens": max_tokens,
                "percent": min(round(current / max_tokens * 100), 100) if max_tokens else 0,
                "last_call_tokens": last_call,
                "total_tokens_used": self.total_tokens_used,
                "compressions": self.compressions,
            })

    async def _manage_memory(self):
        await self.memory_mgr.manage()

    async def _generate_with_stream(self, prompt: str, prefix_log: str = "", use_stream_display: bool = True, response_format=None) -> str:
        self.memory.append({"role": "user", "content": prompt})
        await self._manage_memory()

        tokens_before = self.memory_mgr.count_tokens()
        full_response = ""

        if use_stream_display:
            text = Text(prefix_log)
            with Live(text, refresh_per_second=10, console=game_logger.console):
                def callback(chunk):
                    nonlocal full_response
                    full_response += chunk
                    text.append(chunk)

                response = await self.llm_client.generate_response(self.memory, stream_callback=callback, response_format=response_format)
        else:
            response = await self.llm_client.generate_response(self.memory, response_format=response_format)
            full_response = response

        self.memory.append({"role": "assistant", "content": response})
        tokens_after = self.memory_mgr.count_tokens()
        output_tokens = max(tokens_after - tokens_before, 0)
        input_tokens = self.memory_mgr.count_tokens([{"role": "user", "content": prompt}])
        call_tokens = input_tokens + output_tokens
        self.total_tokens_used += call_tokens
        await self._emit_token_usage(last_call=call_tokens)
        return response

    async def _generate_with_reasoning(self, prompt: str, use_stream_display: bool = True) -> str:
        game_logger.log(f"玩家 {self.player_id} ({self.role.name}) 正在思考...", "dim")
        reasoning = await self._generate_with_stream(
            f"{prompt}\n请先进行一步步的逻辑推理和分析，输出你的思考过程（不需要输出最终决策结果）：",
            f"[dim]玩家 {self.player_id} 思考过程: [/dim]",
            use_stream_display=use_stream_display,
        )
        if self.thinking_callback and reasoning:
            await self.thinking_callback(self.player_id, reasoning)

        final_prompt = "基于以上的思考，请给出你最终的简短决策或发言（不要包含思考过程）："
        self.memory.append({"role": "user", "content": final_prompt})
        await self._manage_memory()

        tokens_before = self.memory_mgr.count_tokens()
        full_response = ""

        if use_stream_display:
            text = Text(f"玩家 {self.player_id}: ")
            with Live(text, refresh_per_second=10, console=game_logger.console):
                def callback(chunk):
                    nonlocal full_response
                    full_response += chunk
                    text.append(chunk)

                response = await self.llm_client.generate_response(self.memory, stream_callback=callback)
        else:
            response = await self.llm_client.generate_response(self.memory)
            full_response = response

        self.memory.append({"role": "assistant", "content": response})
        tokens_after = self.memory_mgr.count_tokens()
        output_tokens = max(tokens_after - tokens_before, 0)
        input_tokens = self.memory_mgr.count_tokens([{"role": "user", "content": final_prompt}])
        call_tokens = input_tokens + output_tokens
        self.total_tokens_used += call_tokens
        await self._emit_token_usage(last_call=call_tokens)
        return response

    async def speak(
        self,
        context: str,
        public_facts: List[str] = [],
        is_endgame: bool = False,
        turn: Optional[int] = None,
        alive_count: Optional[int] = None,
        alive_wolves: Optional[int] = None,
        alive_good: Optional[int] = None,
    ) -> str:
        recent_facts = public_facts[-10:] if len(public_facts) > 10 else public_facts
        facts_str = "\n".join(recent_facts)
        if facts_str:
            facts_str = f"【已证实事实（必须遵守）】\n{facts_str}\n"

        advice = ""
        if is_endgame:
            if self.role.faction == Faction.GOOD:
                advice = '\n【重要战术提示】当前局势紧张（剩余玩家少）。如果你是好人，必须果断站边，不要做“理中客”。一旦某个角色的对立面被系统公告证实为狼人，必须无条件信任该角色的所有历史发言。投错好人就输了！'
            else:
                advice = "\n【重要战术提示】当前局势紧张。如果你是狼人，继续你的伪装，利用好人的犹豫，尝试倒打一耙或混淆视听。"

        status_lines = []
        if turn is not None:
            status_lines.append(f"第{turn}天")
        if alive_count is not None:
            status_lines.append(f"场上还剩{alive_count}人")
        if status_lines:
            urgency = "相对从容"
            if alive_count is not None:
                if alive_count <= 4:
                    urgency = "非常紧急"
                elif alive_count <= 6:
                    urgency = "比较紧张"
            status_lines.append(f"局势{urgency}")
        status_str = ""
        if status_lines:
            status_str = f"【局势信息】{'，'.join(status_lines)}。\n"
        if (
            self.role.faction == Faction.WEREWOLF
            and alive_wolves is not None
            and alive_good is not None
        ):
            remaining_good = max(alive_good - alive_wolves, 0)
            status_str += f"【狼人情报】再击杀{remaining_good}名好人即可达到人数优势胜利。\n"

        prompt = (
            f"{facts_str}{status_str}现在是白天讨论阶段。\n上下文：{context}{advice}"
            "请发表你的观点（100字以内）。\n"
            "你可以在发言末尾用 [🌹玩家N] 表示送花（信任某人），或用 [🍅玩家N] 表示扔西红柿（怀疑某人）。每轮最多一次。\n"
            "示例：我认为3号发言有道理，值得信任。 [🌹3]"
        )

        try:
            if getattr(self.llm_client.config, "is_reasoning", False):
                speech = await self._generate_with_reasoning(prompt)
            else:
                speech = await self._generate_with_stream(prompt, f"玩家 {self.player_id}: ")
        except Exception as e:
            game_logger.log(f"[dim]玩家 {self.player_id} LLM发言调用失败: {e}[/dim]", "red")
            return "（发言失败）"

        import re as _re
        match = _re.search(r"\[([\U0001f339\U0001f345])(\d+)\]", speech)
        if match:
            emoji = match.group(1)
            target = int(match.group(2))
            inter_type = "flower" if "🌹" in emoji else "tomato"
            self.last_interaction = {"type": inter_type, "target": target}
            speech = _re.sub(r"\s*\[[\U0001f339\U0001f345]\d+\]\s*$", "", speech).strip()
        else:
            self.last_interaction = None
        return speech

    async def act(self, action_type: str, options: List[int], public_facts: List[str] = []) -> str:
        if self.role.type == RoleType.IDIOT and self.role.is_revealed and "投票" in action_type:
            return "-1"

        options_with_abstain = options + [-1]
        options_str = str(options)

        recent_facts = public_facts[-10:] if len(public_facts) > 10 else public_facts
        facts_str = "\n".join(recent_facts)
        if facts_str:
            facts_str = f"【已证实事实（必须遵守）】\n{facts_str}\n"

        use_json = getattr(self.llm_client.config, "json_mode", False)

        prompt = f"{facts_str}现在是{action_type}阶段。\n可选目标ID：{options_str}\n如果不确定或想弃票/不使用技能，请回复 -1。\n"

        if use_json:
            prompt += (
                "【重要】请务必输出严格的 JSON 格式，不要包含Markdown代码块（```json ... ```）。\n"
                "格式如下：\n"
                "{\"thought\": \"你的简短思考过程（100字以内）\", \"action\": 目标ID数字}\n"
                "示例：\n"
                "{\"thought\": \"1号发言划水，且攻击了预言家，非常可疑。\", \"action\": 1}\n"
            )
        else:
            if "投票" in action_type:
                prompt += (
                    f"【重要】请先简短陈述投票理由（一句话），然后换行输出数字。\n"
                    f"示例：\n"
                    f"1号发言太划水，不像好人。\n"
                    f"1\n"
                )
            else:
                prompt += (
                    f"【重要】请仅输出一个数字（目标玩家ID或-1），不要包含任何其他文字、标点或解释！\n"
                    f"示例输出：\n"
                    f"1\n"
                    f"-1"
                )

        response = ""
        try:
            if use_json:
                response = (await self._generate_with_stream(
                    prompt, f"玩家 {self.player_id} (行动): ",
                    response_format={"type": "json_object"},
                )).strip()
            elif getattr(self.llm_client.config, "is_reasoning", False):
                response = (await self._generate_with_reasoning(prompt)).strip()
            else:
                response = (await self._generate_with_stream(prompt, f"玩家 {self.player_id} (行动): ")).strip()
        except Exception as e:
            game_logger.log(f"[dim]玩家 {self.player_id} LLM行动调用失败: {e}，默认弃票。[/dim]", "red")
            return "-1"

        return await self.action_parser.parse(
            response=response,
            options=options,
            action_type=action_type,
            player_id=self.player_id,
            use_json=use_json,
            llm_client=self.llm_client,
            on_thinking=self.thinking_callback,
        )

    def update_status(self, alive: bool):
        self.is_alive = alive
