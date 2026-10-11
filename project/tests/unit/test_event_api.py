from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from surveillance.api.app import create_app


def test_event_api_returns_crop_and_shadow_metadata(monkeypatch) -> None:
    event = SimpleNamespace(event_id="00000000-0000-0000-0000-000000000001", camera_id="local",
                            occurred_at=datetime.now(UTC), object_type="car", confidence=0.9,
                            description="Автомобиль на парковке.", risk_level="high", alert_status="pending",
                            object_crop=b"crop")
    assessment = SimpleNamespace(probabilities={"low": 0.1, "medium": 0.1, "high": 0.8},
                                 model_version="danger-v1", mapping_version="mapping-v1",
                                 threshold_policy_version="shadow-v1", mode="shadow")
    task = SimpleNamespace(id=1, status="pending", operator_label=None, operator_note="")

    class Repository:
        def __init__(self, _url):
            pass

        def list_events_page(self, limit, cursor):
            assert limit == 10
            assert cursor is None
            return [{"event": event, "assessment": assessment, "task": task}], None

    monkeypatch.setattr("surveillance.api.routes_events.PostgresEventRepository", Repository)
    class SessionRepository:
        def __init__(self, _url): pass
        def session_user(self, *_args): return SimpleNamespace(id=1, username="viewer", role="viewer")

    monkeypatch.setattr("surveillance.api.app.PostgresEventRepository", SessionRepository)
    response = TestClient(create_app()).get("/api/events?limit=10", cookies={"surveillance_session": "test"})
    assert response.status_code == 200
    payload = response.json()["items"][0]
    assert payload["crop_url"] is None
    assert payload["shadow_task"]["status"] == "pending"
