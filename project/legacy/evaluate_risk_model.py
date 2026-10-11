"""Evaluate a frozen DangerMLP checkpoint on an unseen UCA JSONL split."""
import argparse
import json
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer
from sklearn.metrics import classification_report, confusion_matrix

from surveillance.ml.danger_mlp import DangerMLP
from surveillance.ml.risk_policy import LABELS, RISK_MAPPING
from train_risk_model import embed_rows, load_rows


def evaluate(dataset: Path, checkpoint: Path, cache: Path | None = None) -> dict:
    rows = load_rows(dataset)
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if saved["labels"] != [label.value for label in LABELS]:
        raise ValueError("Checkpoint label order differs from policy")
    encoder = SentenceTransformer("sentence-transformers/LaBSE", device="cpu")
    features = embed_rows(encoder, rows, cache)
    model = DangerMLP()
    model.load_state_dict(saved["state_dict"])
    model.eval()
    with torch.inference_mode():
        predictions = model(features).argmax(dim=1).tolist()
    truth = [LABELS.index(RISK_MAPPING[row["category"]]) for row in rows]
    report = {
        "examples": len(rows),
        "metrics": classification_report(truth, predictions, labels=[0, 1, 2],
                                         target_names=[label.value for label in LABELS],
                                         output_dict=True, zero_division=0),
        "confusion_matrix": confusion_matrix(truth, predictions, labels=[0, 1, 2]).tolist(),
    }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    result = evaluate(args.dataset, args.checkpoint, args.cache)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"examples": result["examples"],
                      "macro_f1": result["metrics"]["macro avg"]["f1-score"],
                      "high_recall": result["metrics"]["high"]["recall"]}, indent=2))
