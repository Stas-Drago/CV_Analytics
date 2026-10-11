# Этап 6: локальный доступ и shadow mode

1. Сделайте backup PostgreSQL, затем примените миграции: `python scripts/apply_migrations.py`.
2. Создайте первого supervisor на локальном хосте: `python scripts/bootstrap_supervisor.py`.
3. При необходимости создайте operator/viewer: `python scripts/create_local_user.py --role operator --username name`.
4. Если пароль локального аккаунта утрачен, смените его интерактивно: `python scripts/reset_local_password.py`.
5. В production за TLS задайте `AUTH_COOKIE_SECURE=true`; в локальной HTTP-разработке оставьте `false`.
6. Для DangerMLP сначала подготовьте aggregate JSON ручной русской оценки с `sample_count`, `macro_f1`, `high_recall`; исходные описания в БД не импортируются.
7. Зарегистрируйте candidate: `python scripts/register_danger_release.py --registered-by supervisor --dataset-version ru-v1 --evaluation-json metrics.json`.
8. Войдите как supervisor и вызовите `POST /api/models/danger/{id}/approve`. Только после этого допустим запуск `scripts/run_analysis_worker.sh risk`.

Approval требует не менее 50 русских примеров, macro-F1 ≥ 0.60 и recall high ≥ 0.75. Даже утверждённая модель создаёт только shadow-задачи; внешние действия и browser notification не включаются.
