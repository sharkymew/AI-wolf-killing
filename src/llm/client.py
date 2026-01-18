from typing import List, Dict, Optional, Any
from openai import AsyncOpenAI
from src.utils.config import ModelConfig
import logging
import asyncio

class LLMClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
        self.logger = logging.getLogger("LLMClient")

    async def generate_response(self, messages: List[Dict[str, str]], stream_callback=None, response_format=None) -> str:
        """
        Generate a response from the LLM based on the conversation history.
        If stream_callback is provided, it will be called with each chunk of text.
        Includes automatic retry mechanism.
        """
        retries = getattr(self.config, "max_retries", 3)
        last_exception = None
        
        # Determine parameters
        kwargs = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        elif getattr(self.config, "json_mode", False):
            kwargs["response_format"] = {"type": "json_object"}

        for attempt in range(retries):
            try:
                if stream_callback:
                    # Stream mode
                    kwargs["stream"] = True
                    stream = await self.client.chat.completions.create(**kwargs)
                    
                    full_content = ""
                    async for chunk in stream:
                        content = chunk.choices[0].delta.content or ""
                        if content:
                            full_content += content
                            stream_callback(content)
                    return full_content
                else:
                    # Non-stream mode
                    kwargs["stream"] = False
                    response = await self.client.chat.completions.create(**kwargs)
                    return response.choices[0].message.content or ""
                    
            except Exception as e:
                last_exception = e
                self.logger.warning(f"LLM {self.config.name} request failed (Attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 * (attempt + 1)) # Exponential backoff
                else:
                    self.logger.error(f"Error calling LLM {self.config.name} after {retries} attempts: {e}")
                    return f"Error: {str(e)}"
        
        return f"Error: {str(last_exception)}"
