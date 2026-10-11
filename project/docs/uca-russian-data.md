# UCA: локальный русский производный набор

Источник — официальные JSON-аннотации UCA/UCF-Crime Annotation: [официальный репозиторий](https://github.com/Xuange923/Surveillance-Video-Understanding). UCA публикуется под Apache-2.0, но оригинальные видео UCF-Crime имеют отдельные условия исследовательского использования; в проект загружаются только текстовые аннотации, без видео.

Перевод выполняется локальной специализированной моделью `Helsinki-NLP/opus-mt-en-ru` в варианте `safetensors`, без внешнего API после её загрузки. Qwen 3B не используется для массового перевода: smoke-проверка показала нестабильный JSON и смешение языков. Исходный текст остаётся в `data/raw`, русские JSONL и manifest — в `data/processed`; обе папки исключены из Git.

Smoke-перевод по десять строк каждого split:

```zsh
.venv/bin/python scripts/download_opus_en_ru.py \
  --target "$HOME/Library/Application Support/CV DATA/model-registry/Helsinki-NLP/opus-mt-en-ru-safetensors-pr6" \
  --manifest models/manifest/opus_mt_en_ru_safetensors.local.json

.venv/bin/python scripts/translate_uca_to_ru.py \
  --train "data/raw/uca_official/UCF Annotation/json/UCFCrime_Train.json" \
  --validation "data/raw/uca_official/UCF Annotation/json/UCFCrime_Val.json" \
  --test "data/raw/uca_official/UCF Annotation/json/UCFCrime_Test.json" \
  --output-dir data/processed/uca_ru_smoke \
  --manifest models/manifest/uca_ru_smoke.local.json \
  --model "$HOME/Library/Application Support/CV DATA/model-registry/Helsinki-NLP/opus-mt-en-ru-safetensors-pr6" \
  --max-rows-per-split 10
```

Полный перевод продолжайте этой же командой без `--max-rows-per-split`, с `--output-dir data/processed/uca_ru` и `--resume` после прерывания. Перед запуском остановите camera-ingest, Qwen vision-worker и другие MLX/YOLO процессы.

Переведённые train/validation/test имеют непересекающиеся `source_video`; их можно передавать в `scripts/train_danger_mlp.py`. Метрики на этом наборе оценивают переносимость с английских UCA-описаний на русские тексты, но **не** заменяют отдельную ручную проверку минимум 50 описаний Qwen с реальной камеры.
