"""Create validated, local-only Russian augmentation data for DangerMLP."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from surveillance.ml.risk_policy import MAPPING_VERSION
from surveillance.ml.synthetic_data import (
    DATASET_VERSION,
    PROMPT_VERSION,
    NearDuplicateIndex,
    build_jobs,
    dataset_sha256,
    json_line,
    label_counts,
    validate_payload,
)


CATEGORY_CONTEXT = {
    "normal": "нейтральная повседневная сцена без явных повреждений, оружия, пламени, столкновения или драки",
    "arrest": "рядом со служебным автомобилем один человек находится в наручниках, рядом стоят другие люди",
    "burglary": "у входной двери видны следы вскрытия или разбитое стекло, без выводов о причине",
    "stealing": "в торговом помещении человек держит товар и сумку рядом с полкой или кассой",
    "shoplifting": "в магазине товар, полки, касса и человек с сумкой видны в одном кадре",
    "vandalism": "на стене, витрине или ограждении видны свежая краска либо физические повреждения",
    "road_accident": "на дороге видны два автомобиля со столкнувшимися кузовами или повреждённым бампером",
    "abuse": "между людьми видны замах, толчок или удар, без выводов о причине",
    "assault": "между людьми видны замах, толчок или удар, без вывода о намерениях",
    "fighting": "двое или несколько людей сцепились, толкают друг друга или наносят удары",
    "arson": "на объекте видны языки пламени и дым",
    "explosion": "в кадре видны яркая вспышка, дым и разлетающиеся обломки",
    "robbery": "у кассы или открытого денежного ящика виден человек в маске, с оружием либо деньгами",
    "shooting": "в руке человека отчётливо видно оружие либо видны вспышка и дым около оружия",
}
BOUNDARY_CONTEXT = {
    "running_person": "человек бежит по тротуару без контакта с другими людьми",
    "group_of_people": "несколько людей стоят рядом без физического конфликта",
    "broken_object": "на земле лежит разбитый бытовой предмет, рядом нет людей",
    "smoke_without_fire": "из вентиляционной трубы видна лёгкая дымка, пламени нет",
    "car_at_roadside": "автомобиль стоит у обочины без повреждений и без столкновения",
    "category_focus": "используй указанный наблюдаемый контекст",
}


def prompt_for(job) -> str:
    return (
        "Сгенерируй одно короткое описание кадра видеонаблюдения на русском языке. "
        "Опиши только видимые факты: объекты, их положение и наблюдаемое действие. "
        "Не называй людей, не описывай лица, не указывай намерения, преступления, инциденты, "
        "диагнозы или степень опасности. Не используй слова «вероятно», «похоже» и «пытается». "
        f"Наблюдаемый контекст: {CATEGORY_CONTEXT[job.category]}. "
        f"Вариант сцены: {BOUNDARY_CONTEXT[job.scenario]}. "
        "Ответь только JSON-объектом без Markdown строго по схеме "
        f'{{"category":"{job.category}","text":"..."}}.'
    )


def parse_output(value: str) -> dict:
    decoder = json.JSONDecoder()
    for index, char in enumerate(value):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(value[index:])
            return payload
        except json.JSONDecodeError:
            continue
    raise ValueError("generator did not return a JSON object")


def call_mlx(*, python_path: Path, helper_path: Path, model_path: Path, jobs: list, timeout: int,
             max_tokens: int) -> dict[str, str]:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".jsonl") as request_file:
        for job in jobs:
            request_file.write(json_line({"id": job.id, "prompt": prompt_for(job), "seed": job.seed}) + "\n")
        request_file.flush()
        completed = subprocess.run(
            [str(python_path), str(helper_path), "--model", str(model_path), "--requests", request_file.name,
             "--max-tokens", str(max_tokens)],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    if completed.returncode:
        raise RuntimeError(f"MLX generator failed: {completed.stderr[-1000:]}")
    outputs: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        try:
            value = json.loads(line)
            if set(value) == {"id", "output"}:
                outputs[str(value["id"])] = str(value["output"])
        except (TypeError, json.JSONDecodeError):
            continue
    return outputs


def load_resume(path: Path) -> tuple[list[dict], NearDuplicateIndex]:
    rows: list[dict] = []
    index = NearDuplicateIndex()
    if not path.exists():
        return rows, index
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows.append(row)
            index.add(row["text"])
    return rows, index


def generate(args) -> dict:
    jobs = build_jobs(per_label=args.per_label, seed=args.seed)
    if args.output.exists() and not args.resume:
        raise FileExistsError(f"output already exists; use --resume: {args.output}")
    accepted, duplicate_index = load_resume(args.output) if args.resume else ([], NearDuplicateIndex())
    accepted_by_id = {row["id"]: row for row in accepted}
    rejections: Counter[str] = Counter()
    pending = [job for job in jobs if job.id not in accepted_by_id]
    attempts: Counter[str] = Counter()
    created_at = datetime.now(UTC).isoformat()
    helper_path = Path(__file__).with_name("mlx_synthetic_generate.py")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    while pending:
        batch, pending = pending[:args.batch_size], pending[args.batch_size:]
        outputs = call_mlx(python_path=args.mlx_python, helper_path=helper_path, model_path=args.model,
                           jobs=batch, timeout=args.timeout_seconds, max_tokens=args.max_tokens)
        retry = []
        new_rows = []
        for job in batch:
            attempts[job.id] += 1
            try:
                row = validate_payload(parse_output(outputs[job.id]), job)
                if duplicate_index.contains_duplicate(row.text):
                    raise ValueError("duplicate or near-duplicate text")
                materialized = row.as_json(generator_version=args.generator_version, created_at=created_at)
                accepted_by_id[job.id] = materialized
                duplicate_index.add(row.text)
                new_rows.append(materialized)
            except (KeyError, ValueError) as error:
                rejections[str(error)] += 1
                if attempts[job.id] < args.max_attempts:
                    retry.append(job)
                else:
                    raise RuntimeError(f"job {job.id} exhausted retries: {error}") from error
        if new_rows:
            with args.output.open("a", encoding="utf-8") as handle:
                for row in new_rows:
                    handle.write(json_line(row) + "\n")
        pending.extend(retry)

    rows = [accepted_by_id[job.id] for job in jobs]
    counts = label_counts(rows)
    if counts != {"low": args.per_label, "medium": args.per_label, "high": args.per_label}:
        raise RuntimeError(f"unexpected class balance: {counts}")
    manifest = {
        "dataset_version": DATASET_VERSION,
        "source": "local-qwen-synthetic-only",
        "status": "training-augmentation-only; not for validation, test, approval, or shadow mode",
        "rows": len(rows),
        "label_counts": counts,
        "policy_mapping_version": MAPPING_VERSION,
        "prompt_version": PROMPT_VERSION,
        "generator_version": args.generator_version,
        "generator_model_path": str(args.model),
        "seed": args.seed,
        "dataset_sha256": dataset_sha256(rows),
        "rejections": dict(sorted(rejections.items())),
        "created_at": created_at,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Generate validated synthetic Russian DangerMLP training data")
    parser.add_argument("--model", type=Path,
                        default=Path("~/Library/Application Support/CV DATA/model-registry/mlx-community/Qwen2.5-VL-3B-Instruct-4bit").expanduser())
    parser.add_argument("--mlx-python", type=Path, default=root / ".venv-mlx/bin/python")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--generator-version", default="mlx-community/Qwen2.5-VL-3B-Instruct-4bit")
    parser.add_argument("--seed", type=int, default=20261010)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--max-tokens", type=int, default=80)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Generate 30 descriptions per label into smoke files")
    args = parser.parse_args()
    if not args.model.is_dir():
        parser.error(f"MLX model was not found: {args.model}")
    if not args.mlx_python.is_file():
        parser.error(f"MLX Python was not found: {args.mlx_python}")
    suffix = ".smoke" if args.smoke else ""
    args.output = args.output or root / f"data/processed/synthetic_risk_v1{suffix}.train.jsonl"
    args.manifest = args.manifest or root / f"models/manifest/synthetic_risk_v1{suffix}.local.json"
    args.per_label = 30 if args.smoke else 2000
    args.batch_size = args.batch_size or (10 if args.smoke else 100)
    print(json.dumps(generate(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
