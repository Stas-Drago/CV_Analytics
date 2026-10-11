"""Local account security primitives; plaintext credentials are never persisted."""

import base64
import hashlib
import hmac
import os
import secrets


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, raw_salt, raw_digest = encoded.split("$")
        if algorithm != "scrypt":
            return False
        expected = hashlib.scrypt(password.encode("utf-8"), salt=base64.urlsafe_b64decode(raw_salt),
                                  n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(expected, base64.urlsafe_b64decode(raw_digest))
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
