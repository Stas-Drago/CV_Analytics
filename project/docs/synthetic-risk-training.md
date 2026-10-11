# Синтетические русские данные для DangerMLP

Набор `synthetic-risk-ru-v1` создаётся только локальной MLX-моделью и является **добавкой к train split**. Он не используется для validation, test, approval, shadow mode или автономных решений.

Перед запуском остановьте camera-ingest, vision-worker, Qdrant-worker и Ollama, чтобы Qwen, LaBSE и YOLO не конкурировали за память Mac с 16 ГБ RAM.

Сначала выполните обязательную smoke-проверку: она создаст 90 строк в отдельных игнорируемых файлах и не затронет полный набор.

```zsh
cd "/Users/stanislav/Documents/Мои проекты/InfoTechSoft/cv-video-surveillance/project"
.venv/bin/python scripts/generate_synthetic_risk_dataset.py --smoke
```

После успешного smoke-теста запустите полный набор:

```zsh
cd "/Users/stanislav/Documents/Мои проекты/InfoTechSoft/cv-video-surveillance/project"
.venv/bin/python scripts/generate_synthetic_risk_dataset.py
```

Скрипт создаст игнорируемые Git файлы:

- `data/processed/synthetic_risk_v1.train.jsonl` — 6 000 строк, по 2 000 на каждый класс;
- `models/manifest/synthetic_risk_v1.local.json` — checksum, версия Qwen, seed, причины отклонения и баланс.

После прерывания продолжите генерацию той же командой с `--resume`. Не изменяйте seed, модель или prompt version в существующем наборе.

Для обучения используйте отдельный draft-registry и передавайте набор только через `--synthetic-train`:

```zsh
.venv/bin/python scripts/train_danger_mlp.py \
  --train data/uca/train.jsonl \
  --validation data/uca/validation.jsonl \
  --test data/uca/test.jsonl \
  --synthetic-train data/processed/synthetic_risk_v1.train.jsonl \
  --registry "${HOME}/Library/Application Support/CV DATA/model-registry/danger-mlp/synthetic-v1" \
  --epochs 12 \
  --license-approved
```

Результат остаётся выпуском `draft`. Его нельзя зарегистрировать как approved, включить в `risk-worker` или применять для alarm/incident до отдельной ручной оценки русских описаний Qwen: минимум 50 примеров, `macro-F1 >= 0.60` и `recall(high) >= 0.75`.
