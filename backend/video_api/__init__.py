"""Пакет video_api — модули backend Video API (вариант A · контроль).

Состав:
    config.py      — константы и переменные окружения (S3, пути, карты).
    models.py      — загрузка модели и SHAP-объяснителя (синглтоны).
    shap_logic.py  — SHAP-расчёты и группировка факторов.
    video_logic.py — планирование видеосегментов.
    schemas.py     — pydantic-схемы запросов/ответов.
    routes.py      — регистрация HTTP-эндпоинтов (register_routes).
"""
