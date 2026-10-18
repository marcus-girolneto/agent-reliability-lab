import json

import httpx
from openai import OpenAI

from agent_reliability_lab.providers import OpenAIProvider
from agent_reliability_lab.tools import READ_TOOLS


def test_responses_adapter_preserves_function_ids_and_usage():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "model": "test-model",
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "output": [
                    {
                        "id": "fc_test",
                        "type": "function_call",
                        "call_id": "call_test",
                        "name": "read_logs",
                        "arguments": '{"service":"checkout"}',
                        "status": "completed",
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "input_tokens_details": {"cached_tokens": 30},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            },
        )

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.model = "test-model"
    provider.client = OpenAI(
        api_key="test-only",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    turn = provider.turn([{"role": "user", "content": "Investigate checkout"}], READ_TOOLS)
    assert turn.calls[0].arguments == {"service": "checkout"}
    assert turn.call_ids == ["call_test"]
    assert turn.output[0].id == "fc_test"
    assert turn.usage.cached_input_tokens == 30
    assert turn.usage.output_tokens == 20
    assert captured[0]["store"] is False
    assert captured[0]["parallel_tool_calls"] is False
    assert captured[0]["max_output_tokens"] == 1500
    provider.client.close()
