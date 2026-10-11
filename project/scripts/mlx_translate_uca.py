"""Translate official UCA sentence annotations into Russian using local MLX Qwen.

Run this script with .venv-mlx/bin/python. It keeps the model loaded once, writes
each accepted row immediately and can therefore resume safely after interruption.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import mlx.core as mx
from mlx_vlm import apply_chat_template, generate, load


VERSION = "uca-ru-local-qwen-v2"
PROMPT_VERSION = "uca-ru-factual-translation-and-filter-v2"
MODEL_VERSION = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
NAMESPACE = uuid.UUID("3212223a-9d76-4b4e-9d4f-8c7f2eb0ee66")
CATEGORY_MAP = {
    "Abuse": "abuse", "Arrest": "arrest", "Arson": "arson", "Assault": "assault",
    "Burglary": "burglary", "Explosion": "explosion", "Fighting": "fighting",
    "Normal": "normal", "RoadAccidents": "road_accident", "Robbery": "robbery",
    "Shooting": "shooting", "Shoplifting": "shoplifting", "Stealing": "stealing", "Vandalism": "vandalism",
}

# A video-level UCA category is not sufficient evidence that every individual
# sentence depicts that category.  Keep a sentence only when it contains a
# direct, observable cue for the category.  This prevents a neutral transition
# frame in (for example) a fighting video from becoming a "high" example.
CATEGORY_SOURCE_CUES = {
    "abuse": ("hit", "slap", "beat", "kick", "push"),
    "arrest": ("handcuff", "police", "arrest", "officer"),
    "arson": ("fire", "flame", "burn", "smoke"),
    "assault": ("hit", "slap", "punch", "kick", "push", "attack"),
    "burglary": ("break", "window", "door", "enter", "climb"),
    "explosion": ("explosion", "explode", "blast", "flame", "smoke"),
    "fighting": ("fight", "punch", "kick", "hit", "push"),
    "road_accident": ("crash", "collision", "hit", "accident", "ran over"),
    "robbery": ("gun", "weapon", "cash", "money", "rob", "threaten"),
    "shooting": ("gun", "weapon", "shoot", "shot", "firearm"),
    "shoplifting": ("take", "hide", "bag", "shelf", "store", "shop"),
    "stealing": ("take", "steal", "bag", "remove", "pick up"),
    "vandalism": ("break", "damage", "spray", "smash", "graffiti"),
}
SOURCE_FORBIDDEN = re.compile(
    r"\b(?:seems?|seemed|appears?|appeared|looks?|looked|think(?:s|ing)?|"
    r"believe(?:s|d)?|bad attitude|aggressive(?:ly)?|rude|angry|suspicious|"
    r"intention|trying to|wants? to|about to|drunk|crazy|disabled)\b", re.IGNORECASE,
)
RUSSIAN_FORBIDDEN = re.compile(
    r"\b(?:кажется|похоже|выглядит|считает|думает|намерен|намеревается|"
    r"пытается|подозрительн\w*|агрессивн\w*|плох\w* отношени\w*|"
    r"инвалид\w*|пьян\w*|безум\w*|страх\w*|жесток\w*|ругал\w*|"
    r"винов\w*|преступлен\w*|инцидент\w*|опасност\w*)\b", re.IGNORECASE,
)
PERSON_APPEARANCE = re.compile(
    r"\b(?:мужчин\w*|женщин\w*|мальчик\w*|девочк\w*|нян\w*|"
    r"одет\w*|рубашк\w*|штан\w*|волос\w*|внешност\w*)\b", re.IGNORECASE,
)


def category_from_video(video_name: str) -> str:
    match = re.match(r"([A-Za-z]+)", video_name)
    if not match or match.group(1) not in CATEGORY_MAP:
        raise ValueError(f"unknown UCA video category: {video_name}")
    return CATEGORY_MAP[match.group(1)]


def rows(source: Path, split: str, max_rows: int | None) -> list[dict]:
    data = json.loads(source.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {category: [] for category in sorted(set(CATEGORY_MAP.values()))}
    for video_name, entry in data.items():
        category = category_from_video(video_name)
        for index, sentence in enumerate(entry["sentences"]):
            normalized = sentence.lower()
            cues = CATEGORY_SOURCE_CUES.get(category, ())
            if SOURCE_FORBIDDEN.search(sentence) or (cues and not any(cue in normalized for cue in cues)):
                continue
            timestamp = entry["timestamps"][index]
            row_id = str(uuid.uuid5(NAMESPACE, f"{split}:{video_name}:{index}"))
            grouped[category].append({
                "id": row_id, "source_video": video_name, "category": category,
                "timestamp_start": timestamp[0], "timestamp_end": timestamp[1], "text_en": sentence,
            })
    if max_rows is None:
        return [row for category in sorted(grouped) for row in grouped[category]]
    # A bounded audit must cover categories, rather than returning only the
    # first category in the source JSON.  Full processing stays unchanged.
    categories = [category for category in sorted(grouped) if grouped[category]]
    base, remainder = divmod(max_rows, len(categories))
    return [row for index, category in enumerate(categories)
            for row in grouped[category][:base + (1 if index < remainder else 0)]]


def prompt(text_en: str) -> str:
    return (
        "Переведи следующее английское описание кадра видеонаблюдения на естественный русский язык. "
        "Сохраняй только наблюдаемые действия и объекты. Удали имена, подробности внешности, "
        "домыслы о мотивах и категоричные утверждения о виновности. Не добавляй новых фактов. "
        "Ответь только JSON-объектом без Markdown: {\"text_ru\":\"...\"}.\n\n"
        f"Текст: {text_en}"
    )


def _validated_russian(value: str) -> str:
    text = " ".join(value.strip().removeprefix("```json").removeprefix("```").removesuffix("```").split())
    if text.startswith("text_ru:"):
        text = text.removeprefix("text_ru:").strip().strip('"')
    letters = [letter for letter in text if letter.isalpha()]
    if len(text) < 3 or len(text) > 700 or not letters:
        raise ValueError("translation length is invalid")
    cyrillic = sum("а" <= item.lower() <= "я" or item.lower() == "ё" for item in letters)
    if cyrillic / len(letters) < 0.60:
        raise ValueError("translation is not Russian")
    return text


def parse_translation(value: str) -> str:
    decoder = json.JSONDecoder()
    for index, char in enumerate(value):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(value[index:])
            return _validated_russian(str(parsed["text_ru"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    raise ValueError("model did not return the required JSON object")


def is_acceptable_translation(value: str) -> bool:
    return not RUSSIAN_FORBIDDEN.search(value) and not PERSON_APPEARANCE.search(value)


def read_completed(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def translate_split(model, processor, items: list[dict], output: Path, args) -> dict:
    completed = read_completed(output) if args.resume else set()
    if output.exists() and not args.resume:
        raise FileExistsError(f"output exists; use --resume: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    accepted = len(completed)
    rejected = 0
    rejection_reasons: dict[str, int] = {}
    rejected_path = output.with_suffix(".rejected.jsonl")
    with output.open("a", encoding="utf-8") as handle:
        for ordinal, item in enumerate(items):
            if item["id"] in completed:
                continue
            error: Exception | None = None
            for attempt in range(args.max_attempts):
                mx.random.seed(args.seed + ordinal * args.max_attempts + attempt)
                rendered = apply_chat_template(processor, model.config, prompt(item["text_en"]), num_images=0)
                response = generate(model, processor, rendered, max_tokens=args.max_tokens,
                                    temp=0, verbose=False)
                try:
                    text_ru = parse_translation(response.text)
                    if not is_acceptable_translation(text_ru):
                        raise ValueError("translation contains prohibited subjective or appearance content")
                    row = {
                        "id": item["id"], "text": text_ru, "category": item["category"],
                        "source_video": item["source_video"], "timestamp_start": item["timestamp_start"],
                        "timestamp_end": item["timestamp_end"], "source": "UCA translated locally",
                        "dataset_version": VERSION, "translation_model": MODEL_VERSION,
                        "translation_prompt_version": PROMPT_VERSION,
                    }
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    handle.flush()
                    accepted += 1
                    break
                except ValueError as caught:
                    error = caught
            else:
                rejected += 1
                reason = str(error or "unknown validation error")
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                with rejected_path.open("a", encoding="utf-8") as rejected_handle:
                    rejected_handle.write(json.dumps({"id": item["id"], "category": item["category"],
                                                      "reason": reason}, ensure_ascii=False) + "\n")
    return {"expected": len(items), "accepted": accepted, "rejected": rejected,
            "rejection_reasons": rejection_reasons, "output_sha256": sha256(output)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--max-tokens", type=int, default=96)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--max-rows-per-split", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    source_paths = {"train": args.train, "validation": args.validation, "test": args.test}
    if not args.model.is_dir() or any(not path.is_file() for path in source_paths.values()):
        raise FileNotFoundError("model or an official UCA JSON file was not found")
    model, processor = load(str(args.model))
    summary = {"dataset_version": VERSION, "source": "UCA official annotations", "source_license": "Apache-2.0",
               "translation_model": MODEL_VERSION, "translation_prompt_version": PROMPT_VERSION,
               "seed": args.seed, "created_at": datetime.now(UTC).isoformat(), "splits": {},
               "source_sha256": {name: sha256(path) for name, path in source_paths.items()}}
    for name, path in source_paths.items():
        summary["splits"][name] = translate_split(model, processor, rows(path, name, args.max_rows_per_split),
                                                   args.output_dir / f"{name}.jsonl", args)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
