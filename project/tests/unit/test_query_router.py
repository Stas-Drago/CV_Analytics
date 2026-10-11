from surveillance.query.router import QueryRouter, QueryTarget


def test_routes_semantic_question_to_qdrant() -> None:
    assert QueryRouter().route("Случалось ли что-то подозрительное?") == QueryTarget.vector


def test_routes_count_with_time_to_sql() -> None:
    assert QueryRouter().route("Сколько машин проехало за последние 3 часа?") == QueryTarget.sql
