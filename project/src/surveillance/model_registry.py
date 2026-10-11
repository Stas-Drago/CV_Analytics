"""Verification for model weights stored outside the repository."""

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_model(model_path: str, manifest_path: str) -> dict:
    weights = Path(model_path).expanduser()
    manifest_file = Path(manifest_path)
    if not weights.is_file():
        raise FileNotFoundError(f"YOLO weights were not found: {weights}")
    if not manifest_file.is_file():
        raise FileNotFoundError(f"YOLO manifest was not found: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected = manifest.get("sha256")
    if not expected or expected.startswith("REPLACE_"):
        raise ValueError("YOLO manifest does not contain a verified SHA-256")
    actual = sha256_file(weights)
    if actual.lower() != expected.lower():
        raise ValueError(f"YOLO checksum mismatch for {weights}: expected {expected}, got {actual}")
    return manifest
