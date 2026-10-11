"""Download YOLO26n into protected storage and write a verified manifest."""

import argparse
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from surveillance.model_registry import sha256_file


DEFAULT_URL = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--manifest", default=Path("models/manifest/yolo26n.json"), type=Path)
    parser.add_argument("--source-url", default=DEFAULT_URL)
    args = parser.parse_args()

    args.target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=args.target.parent, delete=False) as temporary:
        with urlopen(args.source_url) as response:
            shutil.copyfileobj(response, temporary)
        downloaded = Path(temporary.name)
    actual = sha256_file(downloaded)
    if actual.lower() != args.expected_sha256.lower():
        downloaded.unlink(missing_ok=True)
        raise SystemExit(f"Checksum mismatch: expected {args.expected_sha256}, got {actual}")
    downloaded.replace(args.target)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({
        "model": "yolo26n", "ultralytics_version": "8.4.0", "source_url": args.source_url,
        "license": "AGPL-3.0 or Ultralytics Enterprise", "sha256": actual,
        "size_bytes": args.target.stat().st_size, "retrieved_at": datetime.now(UTC).isoformat(),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Verified and stored {args.target}")


if __name__ == "__main__":
    main()
