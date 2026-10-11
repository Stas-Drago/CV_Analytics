from math import sqrt

from sentence_transformers import SentenceTransformer


class LabseEmbedder:
    def __init__(self, model_name: str, model: SentenceTransformer | None = None) -> None:
        # CPU prevents competition with the local YOLO/Ollama Metal workloads.
        self.model = model or SentenceTransformer(model_name, device="cpu")

    def encode(self, text: str) -> list[float]:
        values = self.model.encode(text, normalize_embeddings=True).tolist()
        if len(values) != 768:
            raise ValueError(f"LaBSE embedding must contain 768 values, got {len(values)}")
        norm = sqrt(sum(value * value for value in values))
        if norm == 0:
            raise ValueError("LaBSE returned a zero embedding")
        return [value / norm for value in values]
