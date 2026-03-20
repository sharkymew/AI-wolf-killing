from typing import Callable, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMClientProtocol(Protocol):
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        stream_callback: Optional[Callable[[str], None]] = None,
        response_format: Optional[Dict] = None,
    ) -> str: ...
