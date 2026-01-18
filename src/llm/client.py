from typing import List, Dict, Optional
from openai import AsyncOpenAI
from src.utils.config import ModelConfig
import logging

class LLMClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
        self.logger = logging.getLogger("LLMClient")

    async def generate_response(self, messages: List[Dict[str, str]], stream_callback=None) -> str:
        """
        Generate a response from the LLM based on the conversation history.
        If stream_callback is provided, it will be called with each chunk of text.
        """
        try:
            if stream_callback:
                stream = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature,
                    stream=True
                )
                full_content = ""
                async for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_content += content
                        stream_callback(content)
                return full_content
            else:
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=self.config.temperature
                )
                return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Error calling LLM {self.config.name}: {e}")
            return f"Error: {str(e)}"
