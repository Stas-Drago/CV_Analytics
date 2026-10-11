import hashlib
import json

import pytest

from surveillance.model_registry import validate_model


def test_validate_model_accepts_verified_weights(tmp_path) -> None:
    weights = tmp_path / "yolo26n.pt"
    weights.write_bytes(b"verified weights")
    manifest = tmp_path / "yolo26n.json"
    manifest.write_text(json.dumps({"sha256": hashlib.sha256(weights.read_bytes()).hexdigest()}))
    assert validate_model(str(weights), str(manifest))["sha256"]


def test_validate_model_rejects_wrong_checksum(tmp_path) -> None:
    weights = tmp_path / "yolo26n.pt"
    weights.write_bytes(b"modified weights")
    manifest = tmp_path / "yolo26n.json"
    manifest.write_text(json.dumps({"sha256": "0" * 64}))
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_model(str(weights), str(manifest))
