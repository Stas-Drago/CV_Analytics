import json
from dataclasses import dataclass
from pathlib import Path

import torch

from surveillance.analysis.embeddings import LabseEmbedder
from surveillance.ml.danger_mlp import DangerMLP
from surveillance.ml.risk_policy import LABELS, MAPPING_VERSION, THRESHOLD_POLICY_VERSION
from surveillance.model_registry import sha256_file


@dataclass(frozen=True)
class RiskResult:
    level: str
    probabilities: dict[str, float]
    model_version: str
    model_checksum: str
    mapping_version: str
    threshold_policy_version: str


class DangerMLPRiskScorer:
    """Runtime boundary for the trained DangerMLP release."""

    def __init__(self, model_path: str, manifest_path: str, embedding_model: str,
                 model_card_path: str = "") -> None:
        weights = Path(model_path).expanduser()
        manifest_file = Path(manifest_path)
        if not weights.is_file():
            raise FileNotFoundError(f"DangerMLP weights were not found: {weights}")
        if not manifest_file.is_file():
            raise FileNotFoundError(f"DangerMLP manifest was not found: {manifest_file}")
        self.manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        expected = self.manifest.get("sha256", "")
        actual = sha256_file(weights)
        if not expected or expected != actual:
            raise ValueError("DangerMLP checksum does not match its approved manifest")
        if tuple(self.manifest.get("labels", ())) != LABELS:
            raise ValueError("DangerMLP manifest label order is incompatible")
        if model_card_path:
            card = Path(model_card_path)
            if not card.is_file():
                raise FileNotFoundError(f"DangerMLP model card was not found: {card}")
            self.model_card = card.read_text(encoding="utf-8")
        else:
            self.model_card = ""
        checkpoint = torch.load(weights, map_location="cpu", weights_only=True)
        self.model = DangerMLP()
        self.model.load_state_dict(checkpoint["state_dict"])
        self.model.eval()
        self.embedder = LabseEmbedder(embedding_model)
        self.model_version = str(self.manifest["version"])
        self.model_checksum = actual

    def score(self, description: str) -> RiskResult:
        embedding = torch.tensor([self.embedder.encode(description)], dtype=torch.float32)
        with torch.inference_mode():
            values = torch.softmax(self.model(embedding), dim=1)[0].tolist()
        probabilities = {label: float(values[index]) for index, label in enumerate(LABELS)}
        level = max(probabilities, key=probabilities.get)
        return RiskResult(level=level, probabilities=probabilities, model_version=self.model_version,
                          model_checksum=self.model_checksum, mapping_version=MAPPING_VERSION,
                          threshold_policy_version=THRESHOLD_POLICY_VERSION)
