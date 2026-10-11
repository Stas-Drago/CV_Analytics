"""Offline training only. Input JSONL: text, category, source_video."""
import argparse
import hashlib
import json
import random
from pathlib import Path
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from sentence_transformers import SentenceTransformer
from sklearn.metrics import classification_report, confusion_matrix
from surveillance.ml.danger_mlp import DangerMLP
from surveillance.ml.risk_policy import LABELS, RISK_MAPPING


def load_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    unknown = {row["category"] for row in rows} - set(RISK_MAPPING)
    if unknown:
        raise ValueError(f"Unknown policy categories: {sorted(unknown)}")
    return rows


def embed_rows(encoder: SentenceTransformer, rows: list[dict], cache: Path | None) -> torch.Tensor:
    if cache and cache.exists():
        saved = torch.load(cache, map_location="cpu", weights_only=True)
        return saved["embeddings"]
    features = torch.tensor(
        encoder.encode([row["text"] for row in rows], batch_size=32, show_progress_bar=True),
        dtype=torch.float32,
    )
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"embeddings": features}, cache)
    return features


def train(dataset: Path, validation: Path, output: Path, epochs: int = 12,
          cache_dir: Path | None = None) -> dict:
    random.seed(42)
    torch.manual_seed(42)
    torch.set_num_threads(4)
    rows = load_rows(dataset)
    val_rows = load_rows(validation)
    train_videos = {row["source_video"] for row in rows}
    if train_videos & {row["source_video"] for row in val_rows}:
        raise ValueError("Train/validation video overlap")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    encoder = SentenceTransformer("sentence-transformers/LaBSE", device=device)
    features = embed_rows(encoder, rows, cache_dir / "train.pt" if cache_dir else None)
    val_features = embed_rows(encoder, val_rows, cache_dir / "validation.pt" if cache_dir else None)
    labels = torch.tensor([LABELS.index(RISK_MAPPING[row["category"]]) for row in rows])
    val_labels = torch.tensor([LABELS.index(RISK_MAPPING[row["category"]]) for row in val_rows])
    loader = DataLoader(TensorDataset(features, labels), batch_size=32, shuffle=True)
    model = DangerMLP().to(device)
    counts = torch.bincount(labels, minlength=3).float()
    weights = (counts.sum() / (3 * counts)).to(device)
    loss = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    best_f1 = -1.0
    report: dict = {}
    for epoch in range(epochs):
        model.train()
        for batch, target in loader:
            batch, target = batch.to(device), target.to(device)
            optimizer.zero_grad(); value = loss(model(batch), target); value.backward(); optimizer.step()
        model.eval()
        with torch.inference_mode():
            predictions = model(val_features.to(device)).argmax(dim=1).cpu().tolist()
        truth = val_labels.tolist()
        metrics = classification_report(truth, predictions, labels=[0, 1, 2],
                                        target_names=[label.value for label in LABELS],
                                        output_dict=True, zero_division=0)
        print(f"epoch {epoch + 1}: macro_f1={metrics['macro avg']['f1-score']:.4f} "
              f"high_recall={metrics['high']['recall']:.4f}", flush=True)
        if metrics["macro avg"]["f1-score"] > best_f1:
            best_f1 = metrics["macro avg"]["f1-score"]
            report = {"epoch": epoch + 1, "metrics": metrics,
                      "confusion_matrix": confusion_matrix(truth, predictions, labels=[0, 1, 2]).tolist(),
                      "train_examples": len(rows), "validation_examples": len(val_rows),
                      "device": device}
            output.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": model.cpu().state_dict(),
                        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                        "labels": [label.value for label in LABELS]}, output)
            model.to(device)
            output.with_suffix(".metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--epochs", type=int, default=12)
    args = parser.parse_args()
    train(args.dataset, args.validation, args.output, args.epochs, args.cache_dir)
