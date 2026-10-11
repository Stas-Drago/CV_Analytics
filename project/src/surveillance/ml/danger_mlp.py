import torch
from torch import nn


class DangerMLP(nn.Module):
    """Small project-owned head over a frozen 768-dimensional LaBSE embedding."""

    def __init__(self, input_dim: int = 768, hidden_dim: int = 256, dropout: float = 0.2) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(hidden_dim, 64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64, 3),
        )

    def forward(self, embedding: torch.Tensor) -> torch.Tensor:
        return self.network(embedding)
