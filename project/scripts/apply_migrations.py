"""Small, repeatable SQL migration runner for the local deployment."""

from pathlib import Path

from sqlalchemy import create_engine, text

from surveillance.config import settings


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"


def main() -> None:
    engine = create_engine(settings().database_url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        applied = set(connection.execute(text("SELECT filename FROM schema_migrations")).scalars())
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            if migration.name in applied:
                continue
            connection.connection.driver_connection.execute(migration.read_text(encoding="utf-8"))
            connection.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:filename)"),
                {"filename": migration.name},
            )
            print(f"Applied {migration.name}")


if __name__ == "__main__":
    main()
