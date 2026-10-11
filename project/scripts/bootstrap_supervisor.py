#!/usr/bin/env python3
"""Create the first local supervisor without placing a password in environment files."""

import getpass

from sqlalchemy import select

from surveillance.config import settings
from surveillance.security import hash_password
from surveillance.storage.postgres import PostgresEventRepository, UserRow


def host_database_url() -> str:
    """Translate the Compose-only database hostname for a local macOS CLI."""
    return settings().database_url.replace("@postgres:", "@localhost:")


def main() -> None:
    username = input("Supervisor username: ").strip()
    password = getpass.getpass("Password (12+ characters): ")
    confirm = getpass.getpass("Repeat password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    repository = PostgresEventRepository(host_database_url())
    with repository.sessions() as session:
        if session.scalar(select(UserRow.id).limit(1)):
            raise SystemExit("A local account already exists; bootstrap is disabled")
    repository.create_user(username, hash_password(password), "supervisor")
    print("Supervisor created")


if __name__ == "__main__":
    main()
