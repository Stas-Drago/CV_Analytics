#!/usr/bin/env python3
"""Register a verified DangerMLP candidate; approval remains a supervisor action."""

import argparse
import hashlib
import json
from pathlib import Path

from surveillance.config import settings
from surveillance.model_registry import sha256_file
from surveillance.storage.postgres import PostgresEventRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registered-by", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--evaluation-json", required=True, help="Russian held-out aggregate metrics; no raw texts")
    args = parser.parse_args()
    cfg = settings()
    manifest = json.loads(Path(cfg.danger_model_manifest).read_text(encoding="utf-8"))
    weights = Path(cfg.danger_model_path).expanduser()
    card = Path(cfg.danger_model_card)
    checksum = sha256_file(weights)
    if not manifest.get("version") or str(manifest["version"]).startswith("REPLACE_") or manifest.get("sha256") != checksum:
        raise SystemExit("manifest version/checksum is not an approved candidate")
    metrics = json.loads(Path(args.evaluation_json).read_text(encoding="utf-8"))
    required = {"sample_count", "macro_f1", "high_recall"}
    if not required.issubset(metrics):
        raise SystemExit("evaluation must provide sample_count, macro_f1 and high_recall")
    repository = PostgresEventRepository(cfg.database_url)
    release = repository.register_model_release(version=manifest["version"], checksum=checksum,
        model_card_hash=hashlib.sha256(card.read_bytes()).hexdigest(), mapping_version=manifest["mapping_version"],
        threshold_policy_version=manifest["threshold_policy_version"], dataset_version=args.dataset_version,
        registered_by=args.registered_by)
    repository.add_model_evaluation(release.id, sample_count=int(metrics["sample_count"]),
        macro_f1=float(metrics["macro_f1"]), high_recall=float(metrics["high_recall"]), metrics=metrics,
        language="ru", source="manual-russian-heldout")
    print(f"Registered draft DangerMLP release {release.id}")


if __name__ == "__main__":
    main()
