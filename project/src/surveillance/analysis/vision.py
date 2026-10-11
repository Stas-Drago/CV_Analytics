"""Ollama adapter for factual Russian descriptions of event frames."""

import base64
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError


class VisionPayload(BaseModel):
    description_ru: str = Field(min_length=3, max_length=1000)
    visible_objects: list[str] = Field(default_factory=list, max_length=30)
    observed_actions: list[str] = Field(default_factory=list, max_length=20)
    uncertainty: str = Field(default="", max_length=500)


@dataclass(frozen=True)
class VisionResult:
    description: str
    model_name: str
    model_version: str
    prompt_version: str


SYSTEM_PROMPT = (
    "Ты анализируешь кадр видеонаблюдения. Отвечай только по-русски и только видимыми фактами. "
    "Не идентифицируй людей, не называй личные данные, не предполагай намерения, преступления или инциденты. "
    "Если деталь неразличима, укажи это в uncertainty."
)


class OllamaVisionClient:
    def __init__(self, host: str, model: str, timeout_seconds: float, num_ctx: int,
                 prompt_version: str, client: httpx.Client | None = None) -> None:
        self.host, self.model = host.rstrip("/"), model
        self.timeout_seconds, self.num_ctx, self.prompt_version = timeout_seconds, num_ctx, prompt_version
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def describe(self, frame_jpeg: bytes, object_type: str, confidence: float,
                 bbox: list[int]) -> VisionResult:
        encoded = base64.b64encode(frame_jpeg).decode("ascii")
        instruction = (
            "Опиши наблюдение на изображении в JSON. Детектор сообщил объект "
            f"'{object_type}' с уверенностью {confidence:.2f} и bbox {bbox}. "
            "Сверяй это с изображением, не считай метаданные доказательством."
        )
        response = self.client.post(f"{self.host}/api/chat", json={
            "model": self.model, "stream": False, "keep_alive": "0", "format": VisionPayload.model_json_schema(),
            "options": {"num_ctx": self.num_ctx, "temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": instruction, "images": [encoded]},
            ],
        })
        response.raise_for_status()
        try:
            content = response.json()["message"]["content"]
            payload = VisionPayload.model_validate(json.loads(content))
        except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as error:
            raise ValueError("Ollama returned an invalid vision JSON response") from error
        return VisionResult(description=payload.description_ru.strip(), model_name=self.model,
                            model_version=self.model, prompt_version=self.prompt_version)


def parse_vision_json(content: str) -> VisionPayload:
    """Accept JSON emitted by a local model, ignoring harmless CLI preamble."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(content[index:])
            return VisionPayload.model_validate(value)
        except (json.JSONDecodeError, ValidationError):
            continue
    raise ValueError("Vision model returned an invalid JSON response")


def parse_mlx_description(content: str) -> VisionPayload:
    """MLX 3B is more reliable at concise captions than long schema generation."""
    try:
        return parse_vision_json(content)
    except ValueError:
        text = content.strip().removeprefix("```text").removeprefix("```").removesuffix("```").strip()
        if not text:
            raise ValueError("MLX-VLM returned an empty description")
        return VisionPayload(description_ru=text)


class MlxVisionClient:
    """Isolated MLX-VLM adapter; MLX lives outside the product environment."""

    def __init__(self, python_path: str, model_path: str, timeout_seconds: float, max_tokens: int,
                 prompt_version: str, runner=subprocess.run) -> None:
        self.python_path, self.model_path = python_path, model_path
        self.timeout_seconds, self.max_tokens, self.prompt_version, self.runner = (
            timeout_seconds, max_tokens, prompt_version, runner
        )
        if not Path(model_path).expanduser().is_dir():
            raise FileNotFoundError(f"MLX vision model was not found: {model_path}")
        self.helper_path = Path(__file__).resolve().parents[3] / "scripts" / "mlx_vision_infer.py"

    def describe(self, frame_jpeg: bytes, object_type: str, confidence: float,
                 bbox: list[int]) -> VisionResult:
        prompt = (
            "Опиши изображение одним коротким предложением по-русски и только видимыми фактами. "
            "Не идентифицируй людей, не называй личные данные, "
            "не предполагай намерения, преступления или инциденты. "
            f"Детектор предварительно сообщил объект {object_type}, confidence {confidence:.2f}, bbox {bbox}; "
            "проверь это по изображению."
        )
        image_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image:
                image.write(frame_jpeg)
                image_path = image.name
            completed = self.runner([
                self.python_path, str(self.helper_path), "--model", self.model_path,
                "--max-tokens", str(self.max_tokens), "--prompt", prompt, "--image", image_path,
            ], capture_output=True, text=True, timeout=self.timeout_seconds, check=False)
            if completed.returncode:
                raise RuntimeError(f"MLX-VLM failed: {completed.stderr[-1000:]}")
            payload = parse_mlx_description(completed.stdout)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("MLX-VLM inference timed out") from error
        finally:
            if image_path:
                Path(image_path).unlink(missing_ok=True)
        return VisionResult(description=payload.description_ru.strip(), model_name="mlx-community/Qwen2.5-VL-3B-Instruct-4bit",
                            model_version="4bit", prompt_version=self.prompt_version)


def describe_frame(frame_jpeg: bytes) -> str:
    """Legacy-safe boundary. Workers must create an explicit OllamaVisionClient."""
    raise NotImplementedError("Create OllamaVisionClient with explicit runtime configuration")
