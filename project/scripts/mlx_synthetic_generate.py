"""Generate many text-only JSON responses while loading MLX Qwen only once."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mlx.core as mx
from mlx_vlm import apply_chat_template, generate, load


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch text generation through local MLX-VLM")
    parser.add_argument("--model", required=True)
    parser.add_argument("--requests", type=Path, required=True, help="JSONL with id, prompt and seed")
    parser.add_argument("--max-tokens", type=int, default=140)
    parser.add_argument("--temperature", type=float, default=0.55)
    args = parser.parse_args()

    model, processor = load(args.model)
    for line in args.requests.read_text(encoding="utf-8").splitlines():
        request = json.loads(line)
        mx.random.seed(int(request["seed"]))
        prompt = apply_chat_template(processor, model.config, request["prompt"], num_images=0)
        result = generate(model, processor, prompt, max_tokens=args.max_tokens, temp=args.temperature, verbose=False)
        print(json.dumps({"id": request["id"], "output": result.text}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
