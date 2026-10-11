"""One-shot MLX-VLM inference helper executed from the isolated .venv-mlx."""

import argparse

from mlx_vlm import apply_chat_template, generate, load


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-tokens", type=int, default=160)
    args = parser.parse_args()
    model, processor = load(args.model)
    prompt = apply_chat_template(processor, model.config, args.prompt, num_images=1)
    result = generate(model, processor, prompt, image=[args.image], max_tokens=args.max_tokens,
                      temp=0, verbose=False)
    print(result.text)


if __name__ == "__main__":
    main()
