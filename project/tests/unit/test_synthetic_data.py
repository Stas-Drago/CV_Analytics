import pytest

from surveillance.ml.synthetic_data import GenerationJob, NearDuplicateIndex, build_jobs, validate_payload


def job(category: str, label: str):
    return GenerationJob(id=f"test-{category}", category=category, risk_label=label,
                         scenario="car_at_roadside", seed=7)


def test_jobs_have_exact_balanced_labels() -> None:
    jobs = build_jobs(per_label=2000, seed=20261010)
    assert len(jobs) == 6000
    assert {label: sum(job.risk_label == label for job in jobs) for label in ("low", "medium", "high")} == {
        "low": 2000, "medium": 2000, "high": 2000,
    }


@pytest.mark.parametrize(("category", "label", "text"), [
    ("normal", "low", "У обочины стоит автомобиль, рядом нет других людей."),
    ("road_accident", "medium", "На перекрёстке два автомобиля столкнулись, у одного повреждён бампер."),
    ("arson", "high", "У стены здания видны языки пламени и поднимается дым."),
])
def test_validates_factual_russian_rows(category: str, label: str, text: str) -> None:
    result = validate_payload({"category": category, "text": text}, job(category, label))
    assert result.risk_label == label
    assert result.text == text


def test_rejects_intent_claim() -> None:
    with pytest.raises(ValueError, match="identity, intent, or incident"):
        validate_payload({"category": "robbery", "text": "Человек пытается ограбить магазин у кассы."}, job("robbery", "high"))


@pytest.mark.parametrize("text", [
    "Видимо, у обочины дороги стоит автомобиль без движения.",
    "Несколько людей стоят рядом, возможно, ожидая транспорт.",
    "На дороге авария, в автомобиле находятся пострадавшие.",
    "У обочины стоит автомобиль, в окне видно лицо водителя.",
])
def test_rejects_inference_incident_and_identity_claims(text: str) -> None:
    with pytest.raises(ValueError, match="identity, intent, or incident"):
        validate_payload({"category": "normal", "text": text}, job("normal", "low"))


def test_near_duplicate_index_rejects_rephrased_copy() -> None:
    index = NearDuplicateIndex()
    index.add("У обочины дороги стоит белый автомобиль без движения.")
    assert index.contains_duplicate("У обочины дороги стоит белый автомобиль без движения.")
