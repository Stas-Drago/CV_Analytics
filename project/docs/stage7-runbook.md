# Этап 7: операторский dashboard

## Запуск

1. Заполните локальные `.env` и `.env.host`; секреты не добавляйте в Git.
2. Поднимите инфраструктуру, API и web: `docker compose up -d --build`.
3. Если supervisor ещё не создан, выполните на хосте `python scripts/bootstrap_supervisor.py`.
4. Запустите нужные host-процессы отдельно: camera-ingest, analysis/query workers — только для функций, которые проверяются в текущем сеансе.
5. Откройте `http://127.0.0.1:8080` и войдите локальной учётной записью.

## Доступ по ролям

- `viewer` видит поиск и метаданные событий. Клиент не запрашивает preview, frame, crop и high-очередь.
- `operator` видит камеру, media, high-очередь и выполняет ручные решения.
- `supervisor` имеет возможности operator; управление релизами DangerMLP остаётся в supervisor API Этапа 6.

`high` в интерфейсе всегда подписан «Требует проверки». Confirm/reject фиксируют решение оператора, но не объявляют инцидент и не запускают внешние действия.

## Ручная проверка

1. Войти каждой ролью и проверить, что защищённые media отсутствуют у viewer.
2. Проверить live-preview и статус камеры у operator/supervisor.
3. Перейти вперёд и назад по страницам событий; события не должны пропускаться или повторяться.
4. Выполнить semantic и analytics запросы; убедиться, что вывод структурирован и не показывает raw JSON.
5. Выполнить confirm/reject и shadow label; повторное решение должно показать понятный конфликт `409`.
6. Включить browser notifications явной кнопкой. Новая pending high-задача уведомляется один раз по `task_id`.
7. В тестовых данных передать HTML/JS-строку в описании и комментарии: она должна отображаться как текст.

## Автоматическая проверка

```bash
node --check web/src/*.js
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/surveillance/api src/surveillance/storage tests
```

Dashboard не содержит frontend-framework, внешних UI-зависимостей, драйверов БД, SQL или секретов. Все запросы проходят через `/api` с `credentials: same-origin`.
