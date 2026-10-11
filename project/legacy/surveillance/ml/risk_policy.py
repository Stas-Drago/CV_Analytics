from surveillance.domain import RiskLevel

RISK_MAPPING: dict[str, RiskLevel] = {
    "normal": RiskLevel.low,
    "arrest": RiskLevel.medium, "burglary": RiskLevel.medium, "stealing": RiskLevel.medium,
    "shoplifting": RiskLevel.medium, "vandalism": RiskLevel.medium, "road_accident": RiskLevel.medium,
    "abuse": RiskLevel.high, "assault": RiskLevel.high, "fighting": RiskLevel.high,
    "arson": RiskLevel.high, "explosion": RiskLevel.high, "robbery": RiskLevel.high, "shooting": RiskLevel.high,
}

LABELS = [RiskLevel.low, RiskLevel.medium, RiskLevel.high]
