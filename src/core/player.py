from typing import List, Dict, Optional, Any
from src.core.role import Role, RoleType, Faction
from src.llm.client import LLMClient
from src.llm.prompts import PromptManager
from rich.live import Live
from rich.text import Text
from src.utils.logger import game_logger
import re

class Player:
    def __init__(self, player_id: int, role: Role, llm_client: Any, model_name: str, judge_client: Any = None):
        self.player_id = player_id
        self.role = role
        self.llm_client = llm_client
        self.model_name = model_name
        self.judge_client = judge_client
        self.is_alive = True
        self.memory: List[Dict[str, str]] = []
        
        # Initialize system prompt
        self._init_memory()

    def _init_memory(self):
        # Cast role type to satisfy linter or just pass raw value if enum mismatch
        # Actually RoleType is defined in core/role.py and also in prompts.py separately?
        # Let's check prompts.py imports. Assuming simple string pass works or re-import.
        system_prompt = PromptManager.get_system_prompt(self.role.type, self.player_id)
        self.memory.append({"role": "system", "content": system_prompt})

    def receive_message(self, message: str, is_private: bool = False):
        """Add a message to memory without generating a response."""
        prefix = "[系统通知] " if not is_private else "[私密信息] "
        self.memory.append({"role": "user", "content": f"{prefix}{message}"})

    def _generate_with_stream(self, prompt: str, prefix_log: str = "") -> str:
        """Helper to generate response with streaming output to console."""
        self.memory.append({"role": "user", "content": prompt})
        
        text = Text(prefix_log)
        full_response = ""
        
        with Live(text, refresh_per_second=10, console=game_logger.console):
            def callback(chunk):
                nonlocal full_response
                full_response += chunk
                text.append(chunk)
                
            response = self.llm_client.generate_response(self.memory, stream_callback=callback)
            
        self.memory.append({"role": "assistant", "content": response})
        return response

    def _generate_with_reasoning(self, prompt: str) -> str:
        """
        For reasoning models:
        1. Ask for a thought process (hidden from public but streamed for user visibility).
        2. Ask for the final action/statement based on the thought.
        """
        # Step 1: Reasoning
        reasoning_prompt = f"{prompt}\n请先进行一步步的逻辑推理和分析，输出你的思考过程（不需要输出最终决策结果）："
        
        game_logger.log(f"玩家 {self.player_id} ({self.role.name}) 正在思考...", "dim")
        reasoning = self._generate_with_stream(reasoning_prompt, f"[dim]玩家 {self.player_id} 思考过程: [/dim]")
        
        # Step 2: Final Action
        final_prompt = "基于以上的思考，请给出你最终的简短决策或发言（不要包含思考过程）："
        self.memory.append({"role": "user", "content": final_prompt})
        
        # Stream the final response too
        # game_logger.log(f"玩家 {self.player_id} 正在发言...", "green")
        response = self.llm_client.generate_response(self.memory) # Speak usually handled by caller for logging? 
        # Actually caller logs "Player X: ...", so we should just return string?
        # But user wants to see output AS IT COMES.
        # So we should stream the final response here too.
        
        # Remove the previous user prompt from memory to avoid double append in _generate_with_stream?
        # Actually _generate_with_stream appends.
        # Let's manually handle the second step stream.
        
        text = Text(f"玩家 {self.player_id}: ")
        full_response = ""
        with Live(text, refresh_per_second=10, console=game_logger.console):
            def callback(chunk):
                nonlocal full_response
                full_response += chunk
                text.append(chunk)
            
            response = self.llm_client.generate_response(self.memory, stream_callback=callback)
            
        self.memory.append({"role": "assistant", "content": response})
        return response

    def speak(self, context: str, public_facts: List[str] = [], is_endgame: bool = False) -> str:
        """Generate a public statement."""
        
        # Construct facts section
        facts_str = "\n".join(public_facts)
        if facts_str:
            facts_str = f"【已证实事实（必须遵守）】\n{facts_str}\n"
        
        # Endgame advice
        advice = ""
        if is_endgame:
            if self.role.faction == Faction.GOOD: # Use Faction enum
                 advice = "\n【重要战术提示】当前局势紧张（剩余玩家少）。如果你是好人，必须果断站边，不要做“理中客”。一旦某个角色的对立面被系统公告证实为狼人，必须无条件信任该角色的所有历史发言。投错好人就输了！"
            else:
                 advice = "\n【重要战术提示】当前局势紧张。如果你是狼人，继续你的伪装，利用好人的犹豫，尝试倒打一耙或混淆视听。"

        prompt = f"{facts_str}现在是白天讨论阶段。\n上下文：{context}{advice}\n请发表你的观点（100字以内）："
        
        if getattr(self.llm_client.config, "is_reasoning", False):
            return self._generate_with_reasoning(prompt)
        
        # Normal stream
        return self._generate_with_stream(prompt, f"玩家 {self.player_id}: ")

    def act(self, action_type: str, options: List[int], public_facts: List[str] = []) -> str:
        """Generate a game action (vote, kill, verify, etc.)."""
        # Add abstain option explicitly
        options_with_abstain = options + [-1]
        options_str = str(options)
        
        # Construct facts section
        facts_str = "\n".join(public_facts)
        if facts_str:
            facts_str = f"【已证实事实（必须遵守）】\n{facts_str}\n"
            
        prompt = (
            f"{facts_str}"
            f"现在是{action_type}阶段。\n"
            f"可选目标ID：{options_str}\n"
            f"如果不确定或想弃票/不使用技能，请回复 -1。\n"
        )
        
        # Add voting reasoning requirement
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
        if getattr(self.llm_client.config, "is_reasoning", False):
            # For actions, we might not want to stream the thought process publicly if it reveals too much?
            # But user said "I want to see output every time".
            # Let's stream the reasoning (dimmed) and then the result.
            response = self._generate_with_reasoning(prompt).strip()
        else:
            # For simple actions, maybe just stream the result?
            # Or just return. Usually actions are hidden (night).
            # But if user wants to see...
            # Let's stream it but maybe with a "Secret" prefix if it's night?
            # The prompt says "output your choice".
            response = self._generate_with_stream(prompt, f"玩家 {self.player_id} (行动): ").strip()
            
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
                judge_resp = self.judge_client.generate_response([{"role": "user", "content": judge_prompt}])
                judge_val = judge_resp.strip()
                # Basic validation
                match = re.search(r"(-?\d+)", judge_val)
                if match:
                    extracted = match.group(1)
                    if extracted != response.strip():
                        game_logger.log(f"[dim]裁判判定: 从 '{response}' 提取出 '{extracted}'[/dim]")
                    return extracted
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
                # Log if we extracted something different from full response
                if not self.judge_client and extracted != response: # Only log if judge didn't already
                    game_logger.log(f"[dim]系统自动修正: 从 '{response}' 提取出 '{extracted}'[/dim]")
                return extracted
        except:
            pass
            
        return response

    def update_status(self, alive: bool):
        self.is_alive = alive
