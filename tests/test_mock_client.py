import unittest
import asyncio

from src.utils.config import ModelConfig
from src.llm.mock_client import MockLLMClient


class MockClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_callback_receives_output(self):
        config = ModelConfig(name="Mock", provider="mock", model="mock-model")
        client = MockLLMClient(config)
        chunks = []

        async def run():
            return await client.generate_response(
                [{"role": "user", "content": "测试"}],
                stream_callback=lambda c: chunks.append(c)
            )

        response = await run()
        self.assertTrue(response)
        self.assertTrue(chunks)


if __name__ == "__main__":
    unittest.main()
