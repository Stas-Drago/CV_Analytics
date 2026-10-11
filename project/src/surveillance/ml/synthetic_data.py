"""Validation and deterministic job planning for synthetic DangerMLP training data."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from surveillance.ml.risk_policy import CATEGORY_TO_RISK, MAPPING_VERSION


DATASET_VERSION = "synthetic-risk-ru-v1"
PROMPT_VERSION = "danger-mlp-synthetic-v1"
SYNTHETIC_SOURCE = "synthetic"
NAMESPACE = uuid.UUID("8644a5da-31cc-4c02-930e-a2c594d56a9d")

# These names are scenario tags for diversity; they are not labels returned by the model.
BOUNDARY_SCENARIOS = (
    "running_person", "group_of_people", "broken_object", "smoke_without_fire", "car_at_roadside",
)

CATEGORY_CUES = {
    "normal": (),
    "arrest": ("наруч", "служебн", "патрул", "сопровожд"),
    "burglary": ("разбит", "вскрыт", "открыт", "двер"),
    "stealing": ("товар", "полк", "сумк", "касс"),
    "shoplifting": ("магазин", "товар", "полк", "касс"),
    "vandalism": ("краск", "стен", "витрин", "поврежд"),
    "road_accident": ("автомоб", "столк", "бампер", "дорог", "перекрёст"),
    "abuse": ("удар", "толка", "замах", "человек"),
    "assault": ("удар", "толка", "напад", "человек"),
    "fighting": ("драк", "удар", "сцеп", "толка"),
    "arson": ("плам", "огн", "гор", "дым"),
    "explosion": ("взрыв", "облом", "вспыш", "дым"),
    "robbery": ("касс", "деньг", "маск", "оруж", "вскрыт"),
    "shooting": ("оруж", "выстрел", "пистолет", "дым"),
}

# A neutral road, group of people, smoke without flame, or a parked car are deliberately
# retained as low-risk boundary examples.  Only clear observable danger signals exclude low.
LOW_EXCLUSION_CUES = (
    "наруч", "столк", "поврежд", "разбит", "краск", "плам", "огонь", "гор",
    "взрыв", "облом", "вспыш", "удар", "толка", "драк", "сцеп", "оруж", "выстрел",
)
FORBIDDEN_PATTERNS = (
    r"\b(иван|пётр|петр|сергей|алексей|мария|анна|елена|ольга)\b",
    r"\b(имя|личност|распознан|лиц\w*|паспорт)\b",
    r"\b(намерен|намерева|планиру|с целью|пытается|вероятно|очевидно|похоже|кажется|видимо|"
    r"возможн\w*|может быть|скорее всего)\b",
    r"\b(преступлен|инцидент|винов|опасност|подтвержд|пострадавш|авари\w*|краж\w*|"
    r"ограблен|задержани|вандализм|поджог|нападени|стрельб)\b",
)


class SyntheticPayload(BaseModel):
    """The strict JSON object requested from the local Qwen generator."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: str = Field(min_length=3, max_length=32)
    text: str = Field(min_length=20, max_length=360)


@dataclass(frozen=True)
class GenerationJob:
    id: str
    risk_label: str
    category: str
    scenario: str
    seed: int


@dataclass(frozen=True)
class ValidatedSyntheticRow:
    id: str
    text: str
    risk_label: str
    category: str
    scenario: str
    seed: int

    def as_json(self, *, generator_version: str, created_at: str) -> dict[str, str | int]:
        return {
            "id": self.id,
            "text": self.text,
            "risk_label": self.risk_label,
            "category": self.category,
            "scenario": self.scenario,
            "source": SYNTHETIC_SOURCE,
            "source_video": f"{DATASET_VERSION}:{self.id}",
            "policy_mapping_version": MAPPING_VERSION,
            "generator_version": generator_version,
            "prompt_version": PROMPT_VERSION,
            "seed": self.seed,
            "created_at": created_at,
        }


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).replace("ё", "е")


def _contains_russian_text(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return False
    cyrillic = sum("а" <= char.lower() <= "я" or char.lower() == "ё" for char in letters)
    return cyrillic / len(letters) >= 0.70


def _has_forbidden_content(text: str) -> bool:
    normalized = normalize_text(text)
    return any(re.search(pattern, normalized) for pattern in FORBIDDEN_PATTERNS)


def _has_category_evidence(text: str, category: str) -> bool:
    normalized = normalize_text(text)
    cues = CATEGORY_CUES[category]
    if category == "normal":
        return not any(cue in normalized for cue in LOW_EXCLUSION_CUES)
    return any(cue in normalized for cue in cues)


def validate_payload(payload: Any, job: GenerationJob) -> ValidatedSyntheticRow:
    """Validate one LLM response against the requested category and safety rules."""

    try:
        value = SyntheticPayload.model_validate(payload)
    except ValidationError as error:
        raise ValueError("invalid JSON schema") from error
    if value.category != job.category:
        raise ValueError("returned category does not match the requested category")
    if CATEGORY_TO_RISK.get(value.category) != job.risk_label:
        raise ValueError("category does not match the requested risk label")
    if not _contains_russian_text(value.text):
        raise ValueError("description is not predominantly Russian")
    if _has_forbidden_content(value.text):
        raise ValueError("description contains identity, intent, or incident claims")
    if not _has_category_evidence(value.text, value.category):
        raise ValueError("description lacks visible evidence for its category")
    return ValidatedSyntheticRow(
        id=job.id,
        text=" ".join(value.text.split()),
        risk_label=job.risk_label,
        category=job.category,
        scenario=job.scenario,
        seed=job.seed,
    )


class NearDuplicateIndex:
    """Reject exact and highly similar descriptions without an O(n²) full scan."""

    def __init__(self) -> None:
        self._exact: set[str] = set()
        self._buckets: dict[str, list[str]] = defaultdict(list)

    @staticmethod
    def _keys(text: str) -> set[str]:
        words = normalize_text(text).split()
        if len(words) < 2:
            return {" ".join(words)}
        return {" ".join(words[index:index + 2]) for index in range(len(words) - 1)}

    def add(self, text: str) -> None:
        normalized = normalize_text(text)
        self._exact.add(normalized)
        for key in self._keys(normalized):
            self._buckets[key].append(normalized)

    def contains_duplicate(self, text: str) -> bool:
        normalized = normalize_text(text)
        if normalized in self._exact:
            return True
        candidates = {candidate for key in self._keys(normalized) for candidate in self._buckets[key]}
        return any(SequenceMatcher(a=normalized, b=candidate).ratio() >= 0.92 for candidate in candidates)


def build_jobs(*, per_label: int, seed: int) -> list[GenerationJob]:
    """Return an exact, balanced and reproducible category allocation."""

    if per_label <= 0:
        raise ValueError("per_label must be positive")
    jobs: list[GenerationJob] = []
    for label in ("low", "medium", "high"):
        categories = sorted(category for category, risk in CATEGORY_TO_RISK.items() if risk == label)
        base, remainder = divmod(per_label, len(categories))
        for category_index, category in enumerate(categories):
            for item_index in range(base + (1 if category_index < remainder else 0)):
                ordinal = len(jobs)
                job_id = str(uuid.uuid5(NAMESPACE, f"{DATASET_VERSION}:{seed}:{label}:{category}:{item_index}"))
                jobs.append(GenerationJob(
                    id=job_id,
                    risk_label=label,
                    category=category,
                    scenario=(BOUNDARY_SCENARIOS[ordinal % len(BOUNDARY_SCENARIOS)]
                              if label == "low" else "category_focus"),
                    seed=seed + ordinal,
                ))
    return jobs


def dataset_sha256(rows: list[dict[str, Any]]) -> str:
    canonical = "\n".join(json_line(row) for row in rows).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def json_line(value: dict[str, Any]) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def label_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row["risk_label"]) for row in rows)
    return {label: counts[label] for label in ("low", "medium", "high")}
