from typing import List, Dict, Optional, Callable, Awaitable
from src.core.role import Role, RoleType, Faction
from src.llm.base import LLMClientProtocol
from src.prompts.system import PromptManager
from src.prompts.speak import SpeakContext, build_speak_prompt, parse_interaction
from src.prompts.action import build_action_prompt
from src.core.memory import MemoryManager
from src.core.action_parser import ActionParser
from rich.live import Live
from rich.text import Text
from src.utils.logger import game_logger


class _LLMRunner:
    """统一处理玩家的 LLM 调用 bookkeeping。

    把 append user → manage_memory → token 计数 → 调用 LLM →
    append assistant → emit token usage 这套流程集中起来，让
    `Player.speak` / `Player.act` 等业务方法只关心 prompt 构造和结果。
    """

    def __init__(self, player: "Player"):
        self.player = player

    async def call(
        self,
        prompt: str,
        *,
        prefix_log: str = "",
        use_stream_display: bool = True,
        response_format=None,
    ) -> str:
        p = self.player
        p.memory.append({"role": "user", "content": prompt})
        await p.memory_mgr.manage()

        tokens_before = p.memory_mgr.count_tokens()

        if use_stream_display:
            response = await self._call_with_live_display(
                prefix_log,
                response_format=response_format,
            )
        else:
            response = await p.llm_client.generate_response(
                p.memory, response_format=response_format
            )

        p.memory.append({"role": "assistant", "content": response})

        tokens_after = p.memory_mgr.count_tokens()
        output_tokens = max(tokens_after - tokens_before, 0)
        input_tokens = p.memory_mgr.count_tokens([{"role": "user", "content": prompt}])
        call_tokens = input_tokens + output_tokens
        p.total_tokens_used += call_tokens
        await p._emit_token_usage(last_call=call_tokens)
        return response

    async def _call_with_live_display(self, prefix_log: str, response_format=None) -> str:
        p = self.player
        text = Text(prefix_log)
        full_response = ""
        with Live(text, refresh_per_second=10, console=game_logger.console):
            def callback(chunk):
                nonlocal full_response
                full_response += chunk
                text.append(chunk)

            response = await p.llm_client.generate_response(
                p.memory, stream_callback=callback, response_format=response_format
            )
        return response


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
        self._runner = _LLMRunner(self)

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
        if not self.token_callback:
            return
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

    async def _generate_reasoning_then_answer(
        self,
        prompt: str,
        final_prompt: str,
        *,
        prefix_log: str = "",
        use_stream_display: bool = True,
    ) -> str:
        """两步推理：先输出思考过程，再基于思考给出最终决策。"""
        game_logger.log(f"玩家 {self.player_id} ({self.role.name}) 正在思考...", "dim")
        reasoning = await self._runner.call(
            f"{prompt}\n请先进行一步步的逻辑推理和分析，输出你的思考过程（不需要输出最终决策结果）：",
            prefix_log=f"[dim]玩家 {self.player_id} 思考过程: [/dim]",
            use_stream_display=use_stream_display,
        )
        if self.thinking_callback and reasoning:
            await self.thinking_callback(self.player_id, reasoning)

        return await self._runner.call(
            final_prompt,
            prefix_log=prefix_log,
            use_stream_display=use_stream_display,
        )

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
        speak_ctx = SpeakContext(
            role=self.role,
            public_facts=public_facts,
            is_endgame=is_endgame,
            turn=turn,
            alive_count=alive_count,
            alive_wolves=alive_wolves,
            alive_good=alive_good,
        )
        prompt = build_speak_prompt(speak_ctx, context)

        try:
            if getattr(self.llm_client.config, "is_reasoning", False):
                speech = await self._generate_reasoning_then_answer(
                    prompt,
                    "基于以上的思考，请给出你最终的简短决策或发言（不要包含思考过程）：",
                    prefix_log=f"玩家 {self.player_id}: ",
                )
            else:
                speech = await self._runner.call(prompt, prefix_log=f"玩家 {self.player_id}: ")
        except Exception as e:
            game_logger.log(f"[dim]玩家 {self.player_id} LLM发言调用失败: {e}[/dim]", "red")
            return "（发言失败）"

        cleaned, interaction = parse_interaction(speech)
        self.last_interaction = interaction
        return cleaned

    async def act(self, action_type: str, options: List[int], public_facts: List[str] = []) -> str:
        if self.role.type == RoleType.IDIOT and self.role.is_revealed and "投票" in action_type:
            return "-1"

        use_json = getattr(self.llm_client.config, "json_mode", False)
        prompt = build_action_prompt(action_type, options, public_facts, use_json=use_json)

        try:
            if use_json:
                response = await self._runner.call(
                    prompt,
                    prefix_log=f"玩家 {self.player_id} (行动): ",
                    response_format={"type": "json_object"},
                )
            elif getattr(self.llm_client.config, "is_reasoning", False):
                response = await self._generate_reasoning_then_answer(
                    prompt,
                    "基于以上的思考，请给出你最终的简短决策或发言（不要包含思考过程）：",
                    prefix_log=f"玩家 {self.player_id}: ",
                )
            else:
                response = await self._runner.call(prompt, prefix_log=f"玩家 {self.player_id} (行动): ")
            response = response.strip()
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
