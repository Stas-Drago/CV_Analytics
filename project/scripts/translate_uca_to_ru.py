"""Build Russian UCA train/validation/test JSONL using a local Marian MT model."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


VERSION = "uca-ru-opus-mt-v2"
PROMPT_VERSION = "factual-sanitization-v2"
NAMESPACE = uuid.UUID("3212223a-9d76-4b4e-9d4f-8c7f2eb0ee66")
CATEGORY_MAP = {
    "Abuse": "abuse", "Arrest": "arrest", "Arson": "arson", "Assault": "assault",
    "Burglary": "burglary", "Explosion": "explosion", "Fighting": "fighting",
    "Normal": "normal", "RoadAccidents": "road_accident", "Robbery": "robbery",
    "Shooting": "shooting", "Shoplifting": "shoplifting", "Stealing": "stealing", "Vandalism": "vandalism",
}
RISK_BY_CATEGORY = {
    "normal": "low",
    "arrest": "medium", "burglary": "medium", "stealing": "medium",
    "shoplifting": "medium", "vandalism": "medium", "road_accident": "medium",
    "abuse": "high", "assault": "high", "fighting": "high", "arson": "high",
    "explosion": "high", "robbery": "high", "shooting": "high",
}

# UCA assigns a category to a source video.  A category must not become the
# label of every neutral transition frame from that video, so keep only direct
# observable cues for non-normal categories.
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


def sanitize_source(text: str) -> str:
    """Remove identity and appearance details before translation; keep observable actions."""
    value = text
    replacements = (
        (r"\b(female|male) nanny\b", "person"),
        (r"\b(young|old|elderly) (man|woman|person)\b", "person"),
        (r"\b(man|woman|boy|girl)\b", "person"),
        (r"\bwith (short|long) hair\b", ""),
        (r"\b(slightly )?(fat|thin|strong)\b", ""),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).replace(" ,", ",").strip()


def is_factual_source(text: str) -> bool:
    return bool(text.strip()) and not bool(SOURCE_FORBIDDEN.search(text))


def is_acceptable_translation(text: str) -> bool:
    return is_russian(text) and not bool(RUSSIAN_FORBIDDEN.search(text)) and not bool(PERSON_APPEARANCE.search(text))


def rows(source: Path, split: str, max_rows: int | None, max_per_risk_class: int | None = None) -> list[dict]:
    data = json.loads(source.read_text(encoding="utf-8"))
    result: list[dict] = []
    for video_name, entry in data.items():
        category = category_from_video(video_name)
        for index, sentence in enumerate(entry["sentences"]):
            normalized = sentence.lower()
            cues = CATEGORY_SOURCE_CUES.get(category, ())
            if SOURCE_FORBIDDEN.search(sentence) or (cues and not any(cue in normalized for cue in cues)):
                continue
            start, end = entry["timestamps"][index]
            sanitized = sanitize_source(sentence)
            if not is_factual_source(sanitized):
                continue
            result.append({
                "id": str(uuid.uuid5(NAMESPACE, f"{split}:{video_name}:{index}")),
                "source_video": video_name, "category": category, "timestamp_start": start,
                "timestamp_end": end, "text_en": sanitize_source(sentence),
            })
            if max_rows and len(result) >= max_rows:
                return result
    if max_per_risk_class is None:
        return result
    # Round-robin category selection avoids allowing one common category such
    # as "normal" or "burglary" to dominate its risk class.
    selected: list[dict] = []
    for risk in ("low", "medium", "high"):
        per_category: dict[str, list[dict]] = {}
        for row in result:
            if RISK_BY_CATEGORY[row["category"]] == risk:
                per_category.setdefault(row["category"], []).append(row)
        count = 0
        while per_category and count < max_per_risk_class:
            for category in list(sorted(per_category)):
                if count >= max_per_risk_class:
                    break
                selected.append(per_category[category].pop(0))
                count += 1
                if not per_category[category]:
                    del per_category[category]
    return selected


def is_russian(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if not letters or len(text) < 3 or len(text) > 700:
        return False
    cyrillic = sum("а" <= char.lower() <= "я" or char.lower() == "ё" for char in letters)
    return cyrillic / len(letters) >= 0.60


def is_acceptable_translation(text: str) -> bool:
    return is_russian(text) and not RUSSIAN_FORBIDDEN.search(text) and not PERSON_APPEARANCE.search(text)


def translate(model, tokenizer, items: list[dict], output: Path, *, device: str, batch_size: int,
              resume: bool, model_version: str, forced_bos_token_id: int | None) -> dict:
    if output.exists() and not resume:
        raise FileExistsError(f"output exists; use --resume: {output}")
    completed = set()
    if resume and output.exists():
        completed = {json.loads(line)["id"] for line in output.read_text(encoding="utf-8").splitlines() if line.strip()}
    pending = [item for item in items if item["id"] not in completed]
    output.parent.mkdir(parents=True, exist_ok=True)
    rejected = 0
    with output.open("a", encoding="utf-8") as handle, torch.inference_mode():
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            tokens = tokenizer([item["text_en"] for item in batch], return_tensors="pt", padding=True,
                               truncation=True, max_length=256).to(device)
            generated = model.generate(**tokens, max_new_tokens=256, num_beams=4,
                                       forced_bos_token_id=forced_bos_token_id)
            for item, text in zip(batch, tokenizer.batch_decode(generated, skip_special_tokens=True), strict=True):
                text = " ".join(text.split())
                if not is_acceptable_translation(text):
                    rejected += 1
                    continue
                row = {key: item[key] for key in ("id", "source_video", "category", "timestamp_start", "timestamp_end")}
                row.update({"text": text, "source": "UCA translated locally", "dataset_version": VERSION,
                            "translation_model": model_version, "translation_prompt_version": PROMPT_VERSION})
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
    accepted = sum(1 for line in output.read_text(encoding="utf-8").splitlines() if line.strip())
    return {"expected": len(items), "accepted": accepted, "rejected": rejected, "sha256": sha256(output)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-rows-per-split", type=int)
    parser.add_argument("--max-per-risk-class", type=int,
                        help="Deterministically cap each low/medium/high source pool for a balanced draft.")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source_paths = {"train": args.train, "validation": args.validation, "test": args.test}
    if not args.model.is_dir() or any(not source.is_file() for source in source_paths.values()):
        raise FileNotFoundError("translation model or UCA JSON source is missing")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    if hasattr(tokenizer, "src_lang"):
        tokenizer.src_lang = "eng_Latn"
    forced_bos_token_id = tokenizer.convert_tokens_to_ids("rus_Cyrl") if "nllb" in args.model.name.lower() else None
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model, local_files_only=True).to(device).eval()
    summary = {"dataset_version": VERSION, "source": "official UCA annotations", "source_license": "Apache-2.0",
               "translation_model": str(args.model), "translation_prompt_version": PROMPT_VERSION,
               "device": device, "created_at": datetime.now(UTC).isoformat(), "splits": {},
               "source_sha256": {name: sha256(path) for name, path in source_paths.items()}}
    for name, source in source_paths.items():
        summary["splits"][name] = translate(model, tokenizer, rows(source, name, args.max_rows_per_split,
                                                                      args.max_per_risk_class),
                                              args.output_dir / f"{name}.jsonl", device=device,
                                              batch_size=args.batch_size, resume=args.resume,
                                              model_version=args.model.name, forced_bos_token_id=forced_bos_token_id)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
