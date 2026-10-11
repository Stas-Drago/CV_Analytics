"""Download the approved local English-to-Russian translation model with a manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from huggingface_hub import snapshot_download


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Helsinki-NLP/opus-mt-en-ru")
    parser.add_argument("--revision", default="refs/pr/6", help="Official safetensors revision")
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    snapshot_download(repo_id=args.repo, revision=args.revision, local_dir=args.target, local_dir_use_symlinks=False)
    files = {str(path.relative_to(args.target)): sha256(path) for path in sorted(args.target.rglob("*")) if path.is_file()}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps({
        "model": args.repo, "revision": args.revision, "downloaded_at": datetime.now(UTC).isoformat(), "files": files,
        "purpose": "local UCA English-to-Russian translation only",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
