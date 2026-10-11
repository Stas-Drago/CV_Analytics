"""Convert official UCA JSON annotations to risk-classifier JSONL without copying source data into Git."""
import argparse
import json
import re
from pathlib import Path

ALIASES = {
    "Normal": "normal", "Abuse": "abuse", "Arrest": "arrest", "Arson": "arson",
    "Assault": "assault", "Burglary": "burglary", "Explosion": "explosion", "Fighting": "fighting",
    "RoadAccidents": "road_accident", "Robbery": "robbery", "Shooting": "shooting",
    "Shoplifting": "shoplifting", "Stealing": "stealing", "Vandalism": "vandalism",
}


def category(video_name: str) -> str:
    match = re.match(r"([A-Za-z]+)", video_name)
    if not match or match.group(1) not in ALIASES:
        raise ValueError(f"Unsupported UCA video category: {video_name}")
    return ALIASES[match.group(1)]


def convert(source: Path, target: Path) -> int:
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = []
    for video, value in payload.items():
        for sentence in value["sentences"]:
            rows.append({"text": sentence.strip(), "category": category(video), "source_video": video})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path); parser.add_argument("target", type=Path)
    args = parser.parse_args(); print(f"Prepared {convert(args.source, args.target)} records")
