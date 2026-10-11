# Этап 1: локальный запуск

1. Запустите инфраструктуру: `docker compose up -d postgres redis qdrant migrate api web`.
2. Интерфейс ручной проверки доступен по `http://127.0.0.1:8080`.
3. Убедитесь, что `.env.host` содержит путь к проверенному весу и `YOLO_DEVICE=mps`.
4. Запустите единственный владелец USB-камеры: `sh scripts/run_camera_ingest.sh`.

При отключении камеры процесс остановится, а API сохранит статус `offline` на 60 секунд. Запускать его повторно следует вручную. Видеозапись на диск не создаётся.

## Повторная загрузка веса

Проверенный SHA-256 и URL берутся из официального GitHub release asset. Пример:

```sh
.venv/bin/python scripts/provision_yolo26n.py \
  --target "/Users/stanislav/Library/Application Support/CV DATA/model-registry/yolo26n/8.4.0/yolo26n.pt" \
  --expected-sha256 9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef
```
