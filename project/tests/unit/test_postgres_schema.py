from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from surveillance.storage.postgres import EventRow


def test_event_identifier_compiles_as_postgresql_uuid() -> None:
    statement = str(CreateTable(EventRow.__table__).compile(dialect=postgresql.dialect()))
    assert "event_id UUID NOT NULL" in statement
