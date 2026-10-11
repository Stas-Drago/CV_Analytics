#!/usr/bin/env python3
"""Create an operator or viewer account locally without exposing a password in config."""

import argparse
import getpass

from surveillance.config import settings
from surveillance.security import hash_password
from surveillance.storage.postgres import PostgresEventRepository


def host_database_url() -> str:
    """Translate the Compose-only database hostname for a local macOS CLI."""
    return settings().database_url.replace("@postgres:", "@localhost:")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("viewer", "operator", "supervisor"), required=True)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password (12+ characters): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    PostgresEventRepository(host_database_url()).create_user(args.username, hash_password(password), args.role)
    print(f"Created {args.role} account {args.username}")


if __name__ == "__main__":
    main()
