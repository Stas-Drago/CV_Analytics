from dataclasses import dataclass
from surveillance.domain import RiskLevel

ORDER = {RiskLevel.low: 0, RiskLevel.medium: 1, RiskLevel.high: 2}


@dataclass(frozen=True)
class RiskSignal:
    source: str
    level: RiskLevel
    probability: float
    reason: str


@dataclass(frozen=True)
class FusedRisk:
    level: RiskLevel
    probability: float
    needs_operator_review: bool
    rationale: str


def fuse(text: RiskSignal, vision: RiskSignal) -> FusedRisk:
    """Conservative, explainable ensemble; disagreement never triggers automatic action."""
    if text.level == vision.level:
        return FusedRisk(text.level, (text.probability + vision.probability) / 2,
                         text.level == RiskLevel.high, "both models agree")
    high_signal = next((item for item in (text, vision) if item.level == RiskLevel.high), None)
    if high_signal and high_signal.probability >= 0.85:
        return FusedRisk(RiskLevel.high, high_signal.probability, True,
                         f"high score from {high_signal.source}; second signal disagrees")
    strongest = max((text, vision), key=lambda item: (ORDER[item.level], item.probability))
    return FusedRisk(strongest.level, strongest.probability, True,
                     f"model disagreement: {text.source}={text.level}, {vision.source}={vision.level}")
