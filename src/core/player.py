from typing import List, Dict, Optional, Callable, Awaitable
from src.core.role import Role, RoleType, Faction
from src.llm.base import LLMClientProtocol
from src.llm.prompts import PromptManager
from rich.live import Live
from rich.text import Text
from src.utils.logger import game_logger
import re
import tiktoken
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
        self.compressions = 0

        self._init_memory()

    def _init_memory(self):
        system_prompt = PromptManager.get_system_prompt(self.role.type, self.player_id, self.personality)
        self.memory.append({"role": "system", "content": system_prompt})

    def receive_message(self, message: str, is_private: bool = False):
        """Add a message to memory without generating a response."""
        prefix = "[系统通知] " if not is_private else "[私密信息] "
        self.memory.append({"role": "user", "content": f"{prefix}{message}"})

    def _get_encoding(self):
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            try:
                return tiktoken.get_encoding("gpt2")
            except Exception:
                return None

    def _count_tokens(self, msgs):
        text = "".join(str(m.get("content", "")) for m in msgs)
        enc = self._get_encoding()
        if enc is None:
            chunks = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
            return len(chunks)
        return len(enc.encode(text))

    def _get_max_tokens(self):
        return self.max_memory_tokens if self.max_memory_tokens is not None else getattr(self.llm_client.config, "max_memory_tokens", 2000)

    def _get_current_tokens(self):
        return self._count_tokens(self.memory)

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

    async def _compress_memory(self, to_compress: List[Dict[str, str]]) -> str:
        text = ""
        for m in to_compress:
            role = m.get("role", "?")
            content = m.get("content", "")
            text += f"[{role}]: {content}\n"

        prompt = (
            "请将以下对话历史压缩为一份简洁的摘要，用中文输出。\n"
            "保留以下关键信息：已死亡玩家及身份、已验证的好人/狼人、各方核心观点、关键事件。\n"
            "控制在200字以内。不要包含任何无关内容。\n\n"
            f"{text}"
        )
        try:
            summary = await self.llm_client.generate_response([
                {"role": "system", "content": "你是一个对话摘要助手，请简洁地总结对话历史。"},
                {"role": "user", "content": prompt},
            ])
            summary = summary.strip()
            game_logger.log(f"玩家 {self.player_id} 上下文已压缩 ({len(to_compress)} 条 → 摘要)", "dim")
            return summary
        except Exception as e:
            game_logger.log(f"玩家 {self.player_id} 上下文压缩失败: {e}", "yellow")
            return ""

    async def _manage_memory(self):
        if len(self.memory) <= 1:
            return

        max_tokens = self._get_max_tokens()
        total = self._get_current_tokens()
        if total <= max_tokens:
            return

        system_msg = self.memory[0]
        recent_memory = self.memory[1:]

        kept_msgs = []
        current_tokens = self._count_tokens([system_msg])
        dropped = []

        for msg in reversed(recent_memory):
            msg_tokens = self._count_tokens([msg])
            if current_tokens + msg_tokens > max_tokens:
                dropped.insert(0, msg)
            else:
                kept_msgs.insert(0, msg)
                current_tokens += msg_tokens

        if dropped and len(dropped) >= 4:
            private_msgs = [m for m in dropped if "私密信息" in m.get("content", "")]
            public_dropped = [m for m in dropped if "私密信息" not in m.get("content", "")]
            recent_msgs = kept_msgs[-6:] if len(kept_msgs) > 6 else kept_msgs
            older_kept = kept_msgs[:-6] if len(kept_msgs) > 6 else []

            to_compress = older_kept + public_dropped
            if to_compress:
                summary = await self._compress_memory(to_compress)
                if summary:
                    self.compressions += 1
                    self.memory = [system_msg, {"role": "system", "content": f"[上下文摘要] {summary}"}] + private_msgs + recent_msgs
                    return

        self.memory = [system_msg] + kept_msgs

    async def _generate_with_stream(self, prompt: str, prefix_log: str = "", use_stream_display: bool = True, response_format=None) -> str:
        self.memory.append({"role": "user", "content": prompt})
        await self._manage_memory()

        tokens_before = self._get_current_tokens()
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
        tokens_after = self._get_current_tokens()
        output_tokens = max(tokens_after - tokens_before, 0)
        input_tokens = self._count_tokens([{"role": "user", "content": prompt}])
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

        tokens_before = self._get_current_tokens()
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
        tokens_after = self._get_current_tokens()
        output_tokens = max(tokens_after - tokens_before, 0)
        input_tokens = self._count_tokens([{"role": "user", "content": final_prompt}])
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
        """Generate a public statement."""
        
        recent_facts = public_facts[-10:] if len(public_facts) > 10 else public_facts
        facts_str = "\n".join(recent_facts)
        if facts_str:
            facts_str = f"【已证实事实（必须遵守）】\n{facts_str}\n"

        # Endgame advice
        advice = ""
        if is_endgame:
            if self.role.faction == Faction.GOOD: # Use Faction enum
                 advice = "\n【重要战术提示】当前局势紧张（剩余玩家少）。如果你是好人，必须果断站边，不要做“理中客”。一旦某个角色的对立面被系统公告证实为狼人，必须无条件信任该角色的所有历史发言。投错好人就输了！"
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
        """Generate a game action (vote, kill, verify, etc.)."""
        # Revealed Idiot cannot vote
        if self.role.type == RoleType.IDIOT and self.role.is_revealed and "投票" in action_type:
            return "-1"

        # Add abstain option explicitly
        options_with_abstain = options + [-1]
        options_str = str(options)
        
        recent_facts = public_facts[-10:] if len(public_facts) > 10 else public_facts
        facts_str = "\n".join(recent_facts)
        if facts_str:
            facts_str = f"【已证实事实（必须遵守）】\n{facts_str}\n"

        # Check if JSON mode is enabled for this model
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
            # Add voting reasoning requirement (Text Mode)
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
        # If JSON mode, we don't use 'reasoning' model feature usually, or we use it but still expect JSON.
        # But if use_json is True, we probably want to skip the "thinking" step of _generate_with_reasoning 
        # because the thought is inside the JSON.
        
        try:
            if use_json:
                response = (await self._generate_with_stream(
                    prompt, f"玩家 {self.player_id} (行动): ",
                    response_format={"type": "json_object"},
                )).strip()

                # Parse JSON
                try:
                    # Cleanup potential markdown
                    cleaned = response.replace("```json", "").replace("```", "").strip()
                    data = json.loads(cleaned)

                    thought = data.get("thought", "")
                    action = data.get("action", -1)

                    if thought:
                        game_logger.log(f"[dim]玩家 {self.player_id} 思考: {thought}[/dim]")
                        if self.thinking_callback:
                            await self.thinking_callback(self.player_id, thought)

                    return str(action)
                except json.JSONDecodeError:
                    game_logger.log(f"JSON解析失败，尝试回退到Regex: {response}", "yellow")
                    # Fallthrough to regex/judge

            elif getattr(self.llm_client.config, "is_reasoning", False):
                response = (await self._generate_with_reasoning(prompt)).strip()
            else:
                response = (await self._generate_with_stream(prompt, f"玩家 {self.player_id} (行动): ")).strip()
        except Exception as e:
            game_logger.log(f"[dim]玩家 {self.player_id} LLM行动调用失败: {e}，默认弃票。[/dim]", "red")
            return "-1"
            
        def validate_action(action_value: str) -> Optional[str]:
            try:
                value = int(action_value)
            except (TypeError, ValueError):
                return None
            if value in options_with_abstain:
                return str(value)
            return None

        # Robust parsing: Use Judge Model if available
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
                # Judge output should be very short
                # Judge client is also Async!
                judge_resp = await self.judge_client.generate_response([{"role": "user", "content": judge_prompt}])
                judge_val = judge_resp.strip()
                # Basic validation
                match = re.search(r"(-?\d+)", judge_val)
                if match:
                    extracted = match.group(1)
                    validated = validate_action(extracted)
                    if validated is not None:
                        if extracted != response.strip():
                            game_logger.log(f"[dim]裁判判定: 从 '{response}' 提取出 '{extracted}'[/dim]")
                        return validated
            except Exception as e:
                game_logger.log(f"[dim]裁判判决失败: {e}，回退到正则提取[/dim]")

        # Fallback to Regex
        try:
            # Match number at the end, or just any number if single
            # Handle "投票给1号" -> 1
            # Handle "1" -> 1
            # Handle "-1" -> -1
            match = re.search(r"(-?\d+)(?!.*\d)", response)
            if match:
                extracted = match.group(1)
                validated = validate_action(extracted)
                if validated is not None:
                    # Log if we extracted something different from full response
                    if not self.judge_client and extracted != response: # Only log if judge didn't already
                        game_logger.log(f"[dim]系统自动修正: 从 '{response}' 提取出 '{extracted}'[/dim]")
                    return validated
        except Exception:
            pass

        default_action = "-1"
        game_logger.log(
            f"[dim]玩家 {self.player_id} 无法解析 {action_type} 行为，默认弃票/跳过 ({default_action})。[/dim]"
        )
        return default_action

    def update_status(self, alive: bool):
        self.is_alive = alive
