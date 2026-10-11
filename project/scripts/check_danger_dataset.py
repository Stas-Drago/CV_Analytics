"""Fail closed if a Russian DangerMLP dataset is not usable for draft training."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from surveillance.ml.risk_policy import CATEGORY_TO_RISK


def load(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"{path} has no accepted rows")
    if any({"id", "text", "category", "source_video"} - row.keys() for row in rows):
        raise ValueError(f"{path} has missing required fields")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-per-class", type=int, default=50)
    args = parser.parse_args()

    report: dict[str, object] = {"status": "passed", "minimum_per_class": args.min_per_class, "splits": {}}
    seen_videos: set[str] = set()
    for name, path in (("train", args.train), ("validation", args.validation), ("test", args.test)):
        rows = load(path)
        videos = {row["source_video"] for row in rows}
        if seen_videos & videos:
            raise ValueError(f"source-video leakage into {name}")
        seen_videos |= videos
        labels = Counter(CATEGORY_TO_RISK[row["category"]] for row in rows)
        if any(labels[label] < args.min_per_class for label in ("low", "medium", "high")):
            raise ValueError(f"{name} is imbalanced after filtering: {dict(labels)}")
        report["splits"][name] = {
            "rows": len(rows), "risk_counts": dict(labels),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
