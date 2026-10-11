import hashlib
import json

import pytest
import torch

from surveillance.analysis.risk import DangerMLPRiskScorer
from surveillance.ml.danger_mlp import DangerMLP


class FakeEmbedder:
    def __init__(self, _model: str) -> None:
        pass

    def encode(self, _text: str) -> list[float]:
        return [0.0] * 768


def test_danger_mlp_rejects_unapproved_checksum(tmp_path) -> None:
    weights = tmp_path / "weights.pt"
    torch.save({"state_dict": DangerMLP().state_dict()}, weights)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": "v1", "sha256": "wrong", "labels": ["low", "medium", "high"]}))
    with pytest.raises(ValueError, match="checksum"):
        DangerMLPRiskScorer(str(weights), str(manifest), "fake")


def test_danger_mlp_returns_three_probabilities(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("surveillance.analysis.risk.LabseEmbedder", FakeEmbedder)
    weights = tmp_path / "weights.pt"
    torch.save({"state_dict": DangerMLP().state_dict()}, weights)
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": "v1", "sha256": digest, "labels": ["low", "medium", "high"]}))
    scorer = DangerMLPRiskScorer(str(weights), str(manifest), "fake")
    result = scorer.score("В кадре виден автомобиль")
    assert set(result.probabilities) == {"low", "medium", "high"}
    assert sum(result.probabilities.values()) == pytest.approx(1.0)
