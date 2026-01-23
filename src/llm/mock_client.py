from typing import List, Dict, Optional, Callable
import random
from src.utils.config import ModelConfig

class MockLLMClient:
    def __init__(self, config: ModelConfig):
        self.config = config

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        stream_callback: Optional[Callable[[str], None]] = None,
        response_format: Optional[Dict] = None
    ) -> str:
        response = self._build_response(messages)
        if stream_callback:
            stream_callback(response)
        return response

    def _build_response(self, messages: List[Dict[str, str]]) -> str:
        last_msg = messages[-1]["content"]
        if "请先进行一步步的逻辑推理和分析" in last_msg:
            return "【Mock推理】: 1. 分析当前局势... 2. 怀疑玩家X... 3. 决定采取行动Y。"

        if "基于以上的思考" in last_msg:
            if "投票" in str(messages[-3:]):
                return "1"
            return "我是AI玩家，经过深思熟虑，我认为..."

        if "请输出你的选择" in last_msg or "可选目标" in last_msg:
            try:
                import re
                match = re.search(r"可选目标：\[(.*?)\]", last_msg)
                if match:
                    options = [int(x.strip()) for x in match.group(1).split(',')]
                    return str(random.choice(options))
            except:
                pass
            return "1"

        return "我是AI玩家，我正在思考。"
