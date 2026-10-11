import json

import httpx
import pytest

from surveillance.analysis.vision import OllamaVisionClient


def client_with(handler):
    return OllamaVisionClient("http://ollama.test", "qwen2.5vl:7b", 5, 4096, "test-v1",
                              httpx.Client(transport=httpx.MockTransport(handler)))


def test_vision_client_sends_jpeg_and_validates_russian_json() -> None:
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5vl:7b"
        assert body["messages"][1]["images"]
        return httpx.Response(200, json={"message": {"content": json.dumps({
            "description_ru": "На кадре виден припаркованный автомобиль.",
            "visible_objects": ["автомобиль"], "observed_actions": [], "uncertainty": "",
        })}})
    result = client_with(handler).describe(b"jpeg", "car", 0.9, [1, 2, 3, 4])
    assert result.description.startswith("На кадре")


def test_vision_client_rejects_invalid_json() -> None:
    def handler(_request):
        return httpx.Response(200, json={"message": {"content": "not-json"}})
    with pytest.raises(ValueError, match="invalid vision JSON"):
        client_with(handler).describe(b"jpeg", "car", 0.9, [1, 2, 3, 4])


def test_vision_client_propagates_ollama_error() -> None:
    def handler(_request):
        return httpx.Response(503)
    with pytest.raises(httpx.HTTPStatusError):
        client_with(handler).describe(b"jpeg", "car", 0.9, [1, 2, 3, 4])
