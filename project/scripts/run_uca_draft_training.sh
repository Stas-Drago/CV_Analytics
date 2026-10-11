#!/usr/bin/env bash
# Build a local, balanced Russian UCA draft dataset, validate it, then train DangerMLP.
# The output is always a draft and cannot enable the risk worker or shadow mode.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="${HOME}/Library/Application Support/CV DATA/model-registry/Helsinki-NLP/opus-mt-en-ru-safetensors-pr6"
DATA_DIR="$PROJECT_DIR/data/processed/uca_ru_opus_balanced_v1"
MANIFEST_DIR="$PROJECT_DIR/models/manifest"
REGISTRY_DIR="${HOME}/Library/Application Support/CV DATA/model-registry/danger-mlp/uca-ru-draft-v1"

cd "$PROJECT_DIR"
if [[ -e "$DATA_DIR" || -e "$REGISTRY_DIR" ]]; then
  echo "Refusing to overwrite an existing dataset or model registry output." >&2
  exit 2
fi

.venv/bin/python scripts/translate_uca_to_ru.py \
  --train 'data/raw/uca_official/UCF Annotation/json/UCFCrime_Train.json' \
  --validation 'data/raw/uca_official/UCF Annotation/json/UCFCrime_Val.json' \
  --test 'data/raw/uca_official/UCF Annotation/json/UCFCrime_Test.json' \
  --model "$MODEL_DIR" \
  --output-dir "$DATA_DIR" \
  --manifest "$MANIFEST_DIR/uca_ru_opus_balanced_v1.local.json" \
  --max-per-risk-class 200

.venv/bin/python scripts/check_danger_dataset.py \
  --train "$DATA_DIR/train.jsonl" \
  --validation "$DATA_DIR/validation.jsonl" \
  --test "$DATA_DIR/test.jsonl" \
  --output "$MANIFEST_DIR/uca_ru_opus_balanced_v1.preflight.json" \
  --min-per-class 50

.venv/bin/python scripts/train_danger_mlp.py \
  --train "$DATA_DIR/train.jsonl" \
  --validation "$DATA_DIR/validation.jsonl" \
  --test "$DATA_DIR/test.jsonl" \
  --registry "$REGISTRY_DIR" \
  --epochs 12 \
  --license-approved
