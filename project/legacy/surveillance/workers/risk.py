from pathlib import Path
import torch
from sentence_transformers import SentenceTransformer
from surveillance.domain import RiskLevel
from surveillance.ml.danger_mlp import DangerMLP
from surveillance.ml.risk_policy import LABELS


class RiskScorer:
    def __init__(self, model_path: str, embedding_model: str):
        self.encoder = SentenceTransformer(embedding_model)
        self.model = DangerMLP()
        state = torch.load(model_path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state["state_dict"])
        self.model.eval()

    def score(self, description: str) -> tuple[RiskLevel, float]:
        embedding = self.encoder.encode([description], convert_to_tensor=True)
        with torch.inference_mode():
            probabilities = torch.softmax(self.model(embedding), dim=1)[0]
        index = int(probabilities.argmax())
        return LABELS[index], float(probabilities[index])
