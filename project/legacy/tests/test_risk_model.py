import torch
from surveillance.domain import RiskLevel
from surveillance.ml.danger_mlp import DangerMLP
from surveillance.ml.risk_policy import RISK_MAPPING
from surveillance.fusion import RiskSignal, fuse


def test_danger_mlp_returns_three_logits() -> None:
    assert DangerMLP()(torch.zeros((2, 768))).shape == (2, 3)


def test_all_policy_levels_are_present() -> None:
    assert set(RISK_MAPPING.values()) == {RiskLevel.low, RiskLevel.medium, RiskLevel.high}


def test_high_text_signal_creates_review_when_vision_disagrees() -> None:
    result = fuse(RiskSignal("text", RiskLevel.high, 0.9, "fight"), RiskSignal("vision", RiskLevel.low, 0.8, "empty"))
    assert result.level == RiskLevel.high and result.needs_operator_review
