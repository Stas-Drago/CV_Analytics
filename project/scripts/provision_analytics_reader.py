#!/usr/bin/env python3
"""Explicitly provision the account used only by the host query-worker."""

import os
import sys

import psycopg
from psycopg import sql


ROLE = "surveillance_reader"


def main() -> None:
    password = os.getenv("POSTGRES_READER_PASSWORD")
    database_url = os.getenv("DATABASE_URL")
    if not password or not database_url:
        raise SystemExit("POSTGRES_READER_PASSWORD and DATABASE_URL are required")
    dsn = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            exists = cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)).fetchone()
            if exists:
                cursor.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT").format(
                    sql.Identifier(ROLE), sql.Literal(password)))
            else:
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT").format(
                    sql.Identifier(ROLE), sql.Literal(password)))
            cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {};").format(sql.Identifier(ROLE)))
            cursor.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {};").format(sql.Identifier(ROLE)))
            cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM {};").format(sql.Identifier(ROLE)))
            cursor.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {};").format(
                sql.Identifier(connection.info.dbname), sql.Identifier(ROLE)))
            cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {};").format(sql.Identifier(ROLE)))
            cursor.execute(sql.SQL("GRANT SELECT ON analytics_events TO {};").format(sql.Identifier(ROLE)))
    print("surveillance_reader provisioned with SELECT access to analytics_events only")


if __name__ == "__main__":
    main()
