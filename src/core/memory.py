import re
import tiktoken
from typing import List, Dict, Optional
from src.utils.logger import game_logger


class MemoryManager:
    def __init__(
        self,
        memory: List[Dict[str, str]],
        max_tokens: Optional[int],
        llm_client,
        player_id: int,
    ):
        self.memory = memory
        self.max_tokens = max_tokens
        self.llm_client = llm_client
        self.player_id = player_id
        self.compressions = 0

    def get_encoding(self):
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            try:
                return tiktoken.get_encoding("gpt2")
            except Exception:
                return None

    def count_tokens(self, msgs=None):
        if msgs is None:
            msgs = self.memory
        text = "".join(str(m.get("content", "")) for m in msgs)
        enc = self.get_encoding()
        if enc is None:
            chunks = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
            return len(chunks)
        return len(enc.encode(text))

    def get_max_tokens(self):
        if self.max_tokens is not None:
            return self.max_tokens
        return getattr(self.llm_client.config, "max_memory_tokens", 2000)

    async def compress(self, to_compress: List[Dict[str, str]]) -> str:
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

    async def manage(self):
        if len(self.memory) <= 1:
            return

        max_tokens = self.get_max_tokens()
        total = self.count_tokens()
        if total <= max_tokens:
            return

        system_msg = self.memory[0]
        recent_memory = self.memory[1:]

        kept_msgs = []
        current_tokens = self.count_tokens([system_msg])
        dropped = []

        for msg in reversed(recent_memory):
            msg_tokens = self.count_tokens([msg])
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
                summary = await self.compress(to_compress)
                if summary:
                    self.compressions += 1
                    self.memory[:] = [system_msg, {"role": "system", "content": f"[上下文摘要] {summary}"}] + private_msgs + recent_msgs
                    return

        self.memory[:] = [system_msg] + kept_msgs
