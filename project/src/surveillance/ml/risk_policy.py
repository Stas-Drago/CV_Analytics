LABELS = ("low", "medium", "high")
MAPPING_VERSION = "uca-risk-mapping-v1"
THRESHOLD_POLICY_VERSION = "shadow-argmax-v1"

# This mapping is a training policy, not an assertion that any live observation is an incident.
CATEGORY_TO_RISK = {
    "normal": "low",
    "arrest": "medium", "burglary": "medium", "stealing": "medium", "shoplifting": "medium",
    "vandalism": "medium", "road_accident": "medium",
    "abuse": "high", "assault": "high", "fighting": "high", "arson": "high",
    "explosion": "high", "robbery": "high", "shooting": "high",
}
