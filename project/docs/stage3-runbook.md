# Этап 3: локальный запуск

1. Убедиться, что условия UCA/UCF-Crime проверены и разрешают использование набора.
2. Подготовить JSONL train/validation/test с полями `text`, `category`, `source_video`; видео не должно пересекаться между split.
3. Обучить модель только offline:

```bash
.venv/bin/python scripts/train_danger_mlp.py --license-approved \
  --train data/processed/train.jsonl --validation data/processed/validation.jsonl \
  --test data/processed/test.jsonl \
  --registry "$MODEL_REGISTRY_DIR/danger-mlp/danger-mlp-uca-v2"
```

4. Проверить `metrics.json`, вручную утвердить выпуск и перенести checksum, версию и model card в защищённый registry.
5. Установить vision model: `ollama pull qwen2.5vl:7b`. Сохранить вывод `ollama show qwen2.5vl:7b` рядом с manifest; не называть выпуск Q4_K_M без подтверждения метаданных.
6. В `.env.host` задать `DANGER_MODEL_PATH`, `DANGER_MODEL_MANIFEST`, `DANGER_MODEL_CARD`, `OLLAMA_HOST` и `OLLAMA_MODEL`.
7. Запустить по отдельности: `scripts/run_analysis_worker.sh vision` и `scripts/run_analysis_worker.sh risk`.

До отдельного решения все high-результаты остаются только в очереди shadow-проверки.
