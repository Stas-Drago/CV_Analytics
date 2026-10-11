"""Offline, reproducible training for the project-owned DangerMLP model.

The source JSONL files must contain text, category and source_video and must be
obtained only after the dataset licence has been approved.
"""

import argparse
import hashlib
import json
import random
from pathlib import Path

import torch
from sklearn.metrics import classification_report, confusion_matrix
from sentence_transformers import SentenceTransformer
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from surveillance.ml.danger_mlp import DangerMLP
from surveillance.ml.risk_policy import CATEGORY_TO_RISK, LABELS, MAPPING_VERSION, THRESHOLD_POLICY_VERSION


def load_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    required = {"text", "category", "source_video"}
    if not rows or any(required - set(row) for row in rows):
        raise ValueError(f"{path} must contain text, category and source_video")
    unknown = {row["category"] for row in rows} - set(CATEGORY_TO_RISK)
    if unknown:
        raise ValueError(f"Unknown categories in {path}: {sorted(unknown)}")
    return rows


def ensure_disjoint(*splits: list[dict]) -> None:
    video_sets = [{row["source_video"] for row in split} for split in splits]
    if any(left & right for index, left in enumerate(video_sets) for right in video_sets[index + 1:]):
        raise ValueError("A source video appears in more than one split")


def labels(rows: list[dict]) -> torch.Tensor:
    return torch.tensor([LABELS.index(CATEGORY_TO_RISK[row["category"]]) for row in rows])


def encode(encoder: SentenceTransformer, rows: list[dict]) -> torch.Tensor:
    return torch.tensor(encoder.encode([row["text"] for row in rows], batch_size=32,
                                        show_progress_bar=True, normalize_embeddings=True), dtype=torch.float32)


def report(model: DangerMLP, features: torch.Tensor, truth: torch.Tensor, device: str) -> dict:
    with torch.inference_mode():
        predictions = model(features.to(device)).argmax(dim=1).cpu().tolist()
    actual = truth.tolist()
    metrics = classification_report(actual, predictions, labels=[0, 1, 2], target_names=list(LABELS),
                                    output_dict=True, zero_division=0)
    return {"metrics": metrics, "confusion_matrix": confusion_matrix(actual, predictions, labels=[0, 1, 2]).tolist()}


def validate_synthetic_rows(rows: list[dict]) -> None:
    required = {"id", "text", "category", "risk_label", "source", "source_video", "policy_mapping_version"}
    if not rows or any(required - set(row) for row in rows):
        raise ValueError("synthetic train JSONL has required fields missing")
    if any(row["source"] != "synthetic" for row in rows):
        raise ValueError("synthetic train JSONL must identify every row as synthetic")
    if any(CATEGORY_TO_RISK.get(row["category"]) != row["risk_label"] for row in rows):
        raise ValueError("synthetic train JSONL has a category/risk label mismatch")


def train(train_path: Path, validation_path: Path, test_path: Path, registry: Path, epochs: int,
          synthetic_train_path: Path | None = None) -> dict:
    random.seed(42)
    torch.manual_seed(42)
    torch.set_num_threads(4)
    train_rows, validation_rows, test_rows = map(load_rows, (train_path, validation_path, test_path))
    synthetic_rows: list[dict] = []
    if synthetic_train_path:
        synthetic_rows = load_rows(synthetic_train_path)
        validate_synthetic_rows(synthetic_rows)
        train_rows = train_rows + synthetic_rows
    ensure_disjoint(train_rows, validation_rows, test_rows)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    encoder = SentenceTransformer("sentence-transformers/LaBSE", device="cpu")
    train_features, validation_features, test_features = [encode(encoder, rows) for rows in
                                                           (train_rows, validation_rows, test_rows)]
    train_labels, validation_labels, test_labels = [labels(rows) for rows in
                                                     (train_rows, validation_rows, test_rows)]
    model = DangerMLP().to(device)
    counts = torch.bincount(train_labels, minlength=3).float()
    loss = nn.CrossEntropyLoss(weight=(counts.sum() / (3 * counts)).to(device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    best_f1, best = -1.0, None
    loader = DataLoader(TensorDataset(train_features, train_labels), batch_size=32, shuffle=True)
    for epoch in range(epochs):
        model.train()
        for batch, target in loader:
            optimizer.zero_grad()
            value = loss(model(batch.to(device)), target.to(device))
            value.backward()
            optimizer.step()
        model.eval()
        validation = report(model, validation_features, validation_labels, device)
        macro_f1 = validation["metrics"]["macro avg"]["f1-score"]
        if macro_f1 > best_f1:
            best_f1 = macro_f1
            best = {"epoch": epoch + 1, "validation": validation}
            registry.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": model.cpu().state_dict(), "labels": list(LABELS), "seed": 42}, registry / "danger_mlp.pt")
            model.to(device)
    assert best is not None
    model.load_state_dict(torch.load(registry / "danger_mlp.pt", map_location=device, weights_only=True)["state_dict"])
    best["test"] = report(model, test_features, test_labels, device)
    data_files = [("train", train_path), ("validation", validation_path), ("test", test_path)]
    if synthetic_train_path:
        data_files.append(("synthetic_train", synthetic_train_path))
    best["data_sha256"] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in data_files}
    checksum = hashlib.sha256((registry / "danger_mlp.pt").read_bytes()).hexdigest()
    version = "danger-mlp-synthetic-v1" if synthetic_train_path else "danger-mlp-uca-v2"
    manifest = {"version": version, "sha256": checksum, "labels": list(LABELS),
                "architecture": "DangerMLP 768-256-64-3", "mapping_version": MAPPING_VERSION,
                "threshold_policy_version": THRESHOLD_POLICY_VERSION,
                "synthetic_training_augmentation": bool(synthetic_train_path)}
    (registry / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (registry / "metrics.json").write_text(json.dumps(best, indent=2), encoding="utf-8")
    card = (
        "# DangerMLP model card\n\n"
        "Status: draft candidate; requires real Russian evaluation and human approval before shadow mode.\n\n"
        f"- Version: {manifest['version']}\n- SHA-256: {checksum}\n"
        f"- Labels: {', '.join(LABELS)}\n- Mapping: {MAPPING_VERSION}\n"
        f"- Policy: {THRESHOLD_POLICY_VERSION}\n"
        f"- Synthetic training augmentation: {'yes (training only)' if synthetic_train_path else 'no'}\n"
        f"- Validation macro-F1: {best['validation']['metrics']['macro avg']['f1-score']:.4f}\n"
        f"- Test macro-F1: {best['test']['metrics']['macro avg']['f1-score']:.4f}\n\n"
        "This model prioritises text descriptions and must not autonomously confirm incidents or trigger security actions.\n"
    )
    (registry / "model_card.md").write_text(card, encoding="utf-8")
    return best


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Offline DangerMLP training")
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--synthetic-train", type=Path,
                        help="Validated local synthetic JSONL; train augmentation only, never validation/test")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--license-approved", action="store_true")
    args = parser.parse_args()
    if not args.license_approved:
        parser.error("Training is blocked until the UCA dataset licence is approved")
    train(args.train, args.validation, args.test, args.registry, args.epochs, args.synthetic_train)
