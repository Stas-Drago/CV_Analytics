from surveillance.security import hash_password, verify_password
from surveillance.api.app import create_app
from surveillance.storage.postgres import Base, PostgresEventRepository


def test_scrypt_password_is_verifiable_without_plaintext() -> None:
    encoded = hash_password("a-safe-local-password")
    assert "a-safe-local-password" not in encoded
    assert verify_password("a-safe-local-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_model_release_needs_russian_thresholds(tmp_path) -> None:
    database = f"sqlite:///{tmp_path}/stage6.db"
    Base.metadata.create_all(__import__("sqlalchemy").create_engine(database))
    repository = PostgresEventRepository(database)
    release = repository.register_model_release(version="danger-v2", checksum="a" * 64,
        model_card_hash="b" * 64, mapping_version="mapping", threshold_policy_version="shadow",
        dataset_version="russian-v1", registered_by="supervisor")
    repository.add_model_evaluation(release.id, sample_count=49, macro_f1=.9, high_recall=.9,
                                    metrics={}, language="ru", source="test")
    assert repository.approve_model_release(release.id, "supervisor") is None
    repository.add_model_evaluation(release.id, sample_count=50, macro_f1=.60, high_recall=.75,
                                    metrics={}, language="ru", source="test")
    assert repository.approve_model_release(release.id, "supervisor").status == "approved"


def test_shadow_label_has_one_public_endpoint() -> None:
    routes = [route for route in create_app().routes
              if getattr(route, "path", None) == "/api/alerts/shadow/{task_id}/label"
              and "POST" in getattr(route, "methods", set())]
    assert len(routes) == 1
