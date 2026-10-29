# Control video-app · production-standards (video_app_a_production)

Сервис персонального видео для элитной недвижимости (таунхаусы Подмосковья).
Эта версия проекта подготовлена под production: poetry-окружение, pre-commit,
автоформатирование (black/isort), линтер (ruff), CI (Actions), рефакторинг
монолитных файлов на пакеты и автотесты.

Система, которая по ответам покупателя собирает **уникальный видео-ролик**:
модель классификации определяет подходящий посёлок, SHAP выявляет самые важные
для конкретного покупателя факторы, а из видеофрагментов на Yandex Object
Storage склеивается персональное видео.

## Архитектура

```
                    ┌──────────────────────────────────────────────────┐
                    │              Yandex Object Storage (S3)         │
                    │  video/<поселок>/<категория>/<подкатегория>/*.mp4│
                    │  outputs/user_video_<uuid>.mp4 (результат)      │
                    └────────────▲─────────────────────────▲──────────┘
                                 │ (скачивает куски,       │ (загружает результат)
                                 │  ставит в S3)          │
┌───────────────┐   JSON вектор  │                          │         ┌────────────────────┐
│  FRONTEND     │ ─────────────► └──────────────────────────┘         │   BACKEND          │
│  Streamlit    │   features     │        Yandex Serverless Container │   FastAPI          │
│  app.py       │                │                                    │   main.py          │
│               │ ◄──────────────┘   video_url                        │     - global_best  │
│               │    публичная ссылка                                  │       _model.joblib│
└───────────────┘                                                     │     - xgb_explainer│
                                                                      │       .joblib      │
                                                                      └────────────────────┘
```

### Поток работы

1. **Frontend (Streamlit)** показывает анкету покупателя.
2. Покупатель отвечает: планировка, приоритеты, отделка, наличие детей, семья,
   авто, площадь.
3. Frontend собирает **полный вектор признаков** (как в блокноте:
   обнуление группы → единица выбранного значения → перенос между группами →
   перевод площади в ранг).
4. Frontend отправляет `POST {BACKEND}/generate/` с `{"features": {...}}`.
5. **Backend (Serverless Container)**:
   - загружает `global_best_model.joblib` → предсказывает класс (посёлок);
   - загружает `xgb_explainer.joblib` → считает SHAP и сортирует факторы
     по |вкладу|;
   - скачивает с S3: сначала «общий вид», затем топ-SHAP-фрагменты
     (`MAX_SHAP_FACTORS`, по умолчанию 4);
   - склеивает ролик (moviepy + ffmpeg) и сохраняет в `outputs/`.
6. Backend возвращает публичную ссылку на ролик.
7. Frontend показывает ролик покупателю.

## Структура репозиториев (GitHub)

Рекомендуется **два отдельных репозитория** (или две папки в моно-репо):

```
backend/                     # репозиторий/папка 1 — Yandex Serverless Container
├── Dockerfile
├── requirements.txt
├── main.py                  # FastAPI-приложение
├── deploy.sh                # сборка + деплой в YC
├── .env.example
├── model/                   # .joblib модели (git-lfs или загружаются при деплое)
│   ├── global_best_model.joblib
│   └── xgb_explainer.joblib
└── data/
    └── feature_names.txt    # имена фич (одна на строку)

frontend/                    # репозиторий/папка 2 — Streamlit
├── app.py
├── requirements.txt
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── data/
    └── feature_names.txt    # ДОЛЖЕН совпадать с backend/data/feature_names.txt

.github/
└── workflows/
    ├── backend-deploy.yml   # (опционально) CI/CD деплой в YC на push
    └── frontend-deploy.yml  # (опционально) проверка frontend
```

### Почему два репозитория

- **backend** живёт в Yandex Cloud Serverless Container — ему не нужен фронтенд,
  только модели + S3-доступ. Его деплоим в YC.
- **frontend** живёт на Streamlit Community Cloud (или на VM). Ему нужна только
  ссылка на backend. Разделение упрощает скейлинг и деплой.

> Совет: модели `.joblib` плохо хранить в git (большие, бинарные). Используйте
> [git-lfs](https://git-lfs.com/) или загружайте их при сборке из S3 / отдельного
> репозитория. В `backend/model/` добавьте `.gitkeep`, чтобы папка не была пустой.

## Маппинг SHAP-фактор → папка видео

См. `backend/main.py` — `VIDEO_PATH_MAP`. Ключ = имя фичи модели, значение =
`(категория, подкатегория)` на S3. Например:

```
bin_num__приоритеты_инфраструктура  ->  (priorities, infrastructure)
few_cat__есть_ли_дети_Есть           ->  (children_exist, Yes)
```

Код устойчив к именам файлов/папок: ищет любой `.mp4` внутри нужной подпапки
(пробует `priorities`, `proirities`, `priotrities` и т.п.).

## Как развернуть

1. **Object Storage**: загрузите видео по структуре
   `video/<поселок>/<категория>/<подкатегория>/video1.mp4`. Создайте ключи
   доступа (статический ключ) с правами на бакет.
2. **Backend**: соберите Docker-образ с ffmpeg, положите модели,
   задайте env (S3 + `BACKEND_URL`), задеплойте в Yandex Serverless Container.
   См. `backend/README.md` и `backend/deploy.sh`.
3. **Frontend**: задеплойте на Streamlit Cloud, задайте секрет `BACKEND_URL`.
   См. `frontend/README.md`.

## Основные настройки окружения (backend)

| Переменная | Значение |
|------------|----------|
| `YC_S3_ENDPOINT` | `https://storage.yandexcloud.net` |
| `BUCKET_NAME` | имя бакета |
| `YC_ACCESS_KEY_ID` | статический ключ доступа |
| `YC_SECRET_ACCESS_KEY` | секрет ключа |
| `MODEL_PATH` | `model/global_best_model.joblib` |
| `EXPLAINER_PATH` | `model/xgb_explainer.joblib` |
| `MAX_SHAP_FACTORS` | сколько SHAP-фрагментов после общего вида |

---

## Production-стандарты (что добавлено на практике 2)

### Структура после рефакторинга

```
backend/
├── main.py                  # тонкая точка входа FastAPI (uvicorn main:app)
├── video_api/               # пакет бизнес-логики backend
│   ├── config.py            # env/константы, S3-клиент
│   ├── models.py            # загрузка joblib-модели, синглтоны
│   ├── shap_logic.py        # SHAP-вычисления и группировка факторов
│   ├── video_logic.py       # планирование видео-вариантов
│   ├── schemas.py           # pydantic-схемы запросов/ответов
│   └── routes.py            # эндпоинты: /health, /predict, /generate/, /metrics
├── metrics.py               # сбор технических метрик инференса
├── requirements.txt         # пины для Docker-сборки (не менялись)
└── Dockerfile

frontend/
├── app.py                   # точка входа Streamlit + UTM/телефон-хелперы
├── videoapp/                # пакет UI-логики
│   ├── theme.py             # CSS, токены, assets
│   ├── settings.py          # BACKEND_URL, справочники посёлков
│   ├── features.py          # вектор признаков, SHAP, локальная модель
│   ├── landing.py           # hero/values/steps/projects
│   ├── questionnaire.py     # анкета покупателя + лид-форма
│   ├── shap_views.py        # графики важности/waterfall/сравнение
│   ├── video_views.py       # видео-плеер и таблица сегментов
│   └── flow.py              # main() — основной сценарий
├── analytics.py             # продуктовая аналитика (session/lead)
└── requirements.txt         # пины для Streamlit Cloud (не менялись)

tests/                       # unit (58) + live api (5), pytest
.github/workflows/           # lint + tests (+ deploy/keep-warm)
pyproject.toml               # poetry: deps + black + isort + ruff + mypy + pytest
poetry.lock                  # зафиксированные версии всего окружения
.pre-commit-config.yaml      # хуки: black, isort, ruff, sanity-checks
docs/model_lifecycle.md      # диаграммы эксплуатации, мониторинга и переобучения
```

### Poetry и виртуальное окружение

Зависимости всех компонентов (frontend + backend ML-стек + dev-инструменты)
живут в **одном pyproject.toml**; версии зафиксированы в `poetry.lock`.
ML-стек специально заперт на `numpy<2` + `scikit-learn==1.5.2` + `shap==0.45`
(см. комментарии в pyproject) — это же связка задана в `backend/requirements.txt`
для Docker-образа, чтобы pickle-модель и локальный venv были совместимы.

```bash
# 1. Установка poetry (один раз)
pip install poetry

# 2. По умолчанию poetry создаёт .venv В КОРНЕ проекта (настроено в pyproject).
poetry install                     # поднимет .venv и поставит все зависимости + dev-группу

# 3. Работа внутри окружения
poetry run python -m pytest tests/ -m "not api" -q
poetry run streamlit run frontend/app.py
cd backend && poetry run uvicorn main:app --port 8080
```

Окружение **не коммитится** (`.venv/` в .gitignore). В git идут
`pyproject.toml` + `poetry.lock` — этого достаточно, чтобы любой с `poetry`
воспроизвёл байт-в-байт те же версии библиотек.

### Pre-commit и линтеры

```bash
poetry run pre-commit install         # включить хуки (git commit будет проверять)
poetry run pre-commit run --all-files # проверить/поправить всё вручную
```

На каждый коммит прогоняются:

| Инструмент | Что делает |
|---|---|
| `black` (line-length 100) | автоформатирование кода |
| `isort` (profile black) | сортировка импортов |
| `ruff` | линтер (pyflakes/pycodestyle/pyupgrade/bugbear), автофиксы |
| pre-commit-hooks | trailing-whitespace, EOF, check-yaml/toml, merge-conflict |

Конфигурации — в `pyproject.toml` (секции `[tool.black]`, `[tool.isort]`,
`[tool.ruff]`, `[tool.mypy]`), сами хуки — в `.pre-commit-config.yaml`.

### CI (GitHub Actions)

- `lint.yml` — ruff + `black --check` + `isort --check` на poetry-окружении;
- `tests.yml` — poetry install → `pytest -m "not api"` → live api-тесты при
  наличии секрета `BACKEND_URL`;
- `backend-deploy.yml`, `keep-warm.yml` — деплой в Yandex Cloud (unchanged).

### Как просчитывалась жизнь проекта (сводка настроек)

| Файл | Роль |
|---|---|
| `pyproject.toml` | все зависимости + DEV-группа + config форматтеров/линтеров/pytest |
| `poetry.lock` | резолв версий (воспроизводимость окружения) |
| `.pre-commit-config.yaml` | хуки качества на каждый коммит |
| `.gitattributes` | единые LF для скриптов/Dockerfile |
| `.gitignore` | исключает .venv, секреты, mp4-медиа, выгрузки метрик |
