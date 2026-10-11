#!/usr/bin/env python3
"""Reset a local account password without placing credentials in config files."""

import getpass

from sqlalchemy import select

from surveillance.config import settings
from surveillance.security import hash_password
from surveillance.storage.postgres import PostgresEventRepository, UserRow


def host_database_url() -> str:
    """Translate the Compose-only database hostname for a local macOS CLI."""
    return settings().database_url.replace("@postgres:", "@localhost:")


def main() -> None:
    username = input("Username: ").strip()
    password = getpass.getpass("New password (12+ characters): ")
    confirm = getpass.getpass("Repeat new password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    repository = PostgresEventRepository(host_database_url())
    with repository.sessions.begin() as session:
        user = session.scalar(select(UserRow).where(UserRow.username == username, UserRow.active.is_(True)))
        if not user:
            raise SystemExit("Active local account was not found")
        user.password_hash = hash_password(password)
    print("Password updated")


if __name__ == "__main__":
    main()
