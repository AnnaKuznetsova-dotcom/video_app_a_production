# Control video-app · production-standards (video_app_a_production)

Сервис подбора посёлка с готовым видеороликом для элитной недвижимости
(таунхаусы Подмосковья, застройщик KASKAD). Эта версия проекта подготовлена
под production: poetry-окружение, pre-commit, автоформатирование (black/isort),
линтеры (ruff + flake8), CI (Actions), рефакторинг монолитных файлов в пакет
**backend/pipeline/** разбитый по этапам ML-конвейера, автотесты.

Система, которая по ответам покупателя **подбирает посёлок** и показывает
готовый видеоролик этого посёлка (вариант A: ролик фиксированный и не зависит
от индивидуальных ответов — класс → готовое видео).

## Архитектура

```
┌───────────────┐   JSON вектор признаков                       ┌────────────────────┐
│  FRONTEND     │ ─────────────► Yandex Serverless Container    │   BACKEND          │
│  Streamlit    │   POST /generate/                             │   FastAPI          │
│  app.py       │                                               │   main.py          │
│               │ ◄──────────────  публичная ссылка video_url ──│  pipeline/         │
└───────────────┘                                               └─────────┬──────────┘
                                                                          │ фиксированный
                                                                          ▼ ролик посёлка
                                       ┌──────────────────────────────────────────────┐
                                       │        Yandex Object Storage (S3)            │
                                       │  video/Kaskad_Video/<Посёлок>.mp4            │
                                       │  metrics/  (тех. метрики — синхронизация)    │
                                       └──────────────────────────────────────────────┘
```

### Поток работы (вариант A · контроль)

1. **Frontend (Streamlit)** показывает анкету покупателя (9 вопросов + площадь).
2. Покупатель отвечает: планировка, приоритеты, отделка, цель, схема,
   семья, дети, авто, площадь.
3. Frontend собирает **полный вектор признаков** (как в блокноте:
   обнуление группы → единица выбранного значения → перенос между группами →
   ранг площади) — `frontend/videoapp/features.py`.
4. Frontend отправляет `POST {BACKEND}/generate/` с `{"features": {...}}`.
5. **Backend (Serverless Container, `backend/pipeline/`)**:
   - `data_preprocessing` — вектор → DataFrame 42 колонок модели;
   - `model_inference` — `global_best_model.joblib` → класс (посёлок);
   - отдаёт **фиксированный ролик посёлка** из S3 `video/Kaskad_Video/`
     (локальный режим — из `backend/media/`);
   - `metrics_tracker` — пишет инференс в CSV (+ S3-синхронизация).
6. Backend возвращает публичную ссылку на ролик + `stage_timing_ms`.
7. Frontend показывает ролик покупателю и лид-форму.

## Конвейер backend по этапам (backend/pipeline/)

```
backend/
├── main.py                    # тонкая точка входа FastAPI (uvicorn main:app)
├── pipeline/                  # один файл = один этап конвейера
│   ├── config.py              # этап 0: env, S3, карты класс → посёлок → ролик
│   ├── data_preprocessing.py  # этап 1: JSON-вектор → DataFrame модели
│   ├── feature_generation.py  # этап 2: контракт пространства признаков анкеты
│   ├── model_inference.py     # этап 3: joblib-модель, predict, cold/warm
│   ├── model_registry.py      # этап 4: версии модели (versions/ + active_model.txt)
│   ├── model_update/          # этап 5: авто-пайплайн переобучения (Model_retrain_BPMN.md)
│   │   ├── dataset_validation.py
│   │   ├── training.py
│   │   ├── evaluation.py
│   │   ├── promotion.py
│   │   └── README.md
│   ├── metrics_tracker.py     # этап 6: техметрики инференса (CSV + S3)
│   └── serving/routes.py      # этап 7: HTTP-эндпоинты
├── Dockerfile
├── requirements.txt           # пины для Docker-сборки
├── data/feature_names.txt     # имена фич (одна на строку)
└── model/                     # global_best_model.joblib (+ versions/, реестр)
```

frontend/ остаётся как раньше (Streamlit +vedapp), при том что feature
generation (сборка вектора) — это фронт-этап этапa 2.

## Источник расчёта модели

Ноутбук с расчётом (Colab, прототип): анкета → вектор признаков → классификация;
структура видеофайлов `video/<посёлок>/<категория>/<подкатегория>/video1.mp4`:
<https://colab.research.google.com/drive/11DuvWTXvnml5HbQoV3ubGGYTxtuUFP8a?usp=sharing>

## Документы обучения (Homework)

| Файл | О чём |
|---|---|
| [`model_card.md`](model_card.md) | Model Card (по шаблону Google): цель, метрики, ограничения, bias, версия данных, источник |
| [`Model_BPMN.md`](Model_BPMN.md) | BPMN: место модели в бизнес-процессе (разработка → валидация → утверждение → деплой → мониторинг → переобучение) |
| [`Model_retrain_BPMN.md`](Model_retrain_BPMN.md) | BPMN переобучения: триггеры (**новый посёлок = новый класс**), числовые пороги, канареечный деплой, rollback |
| [`Model_retrain_decision_card.md`](Model_retrain_decision_card.md) | Карточка-отчёт менеджера: режим A (штатное авто-переобучение) и режим B (новый класс, полная ручная верификация) |
README.md table for docs, then run checks (black/flake8/isort) and commit+push.</think><tool_call>edit<arg_key>newString</arg_key><arg_value>| [`docs/model_lifecycle.md`](docs/model_lifecycle.md) | Диаграммы эксплуатации, мониторинга, переобучения (вариант 1 подробный + вариант 2 для менеджмента, горизонтальный) |
| [`docs/poetry_quickstart.md`](docs/poetry_quickstart.md) | Краткая справка по Poetry: этапы создания окружения |
| [`METRICS.md`](METRICS.md) | Метрики приложения: что измеряется и как смотреть |
| [`AUTOTESTS.md`](AUTOTESTS.md) | Автотесты метрик: pytest + ручные проверки |

## Как развернуть

1. **Object Storage**: загрузите ролики по структуре
   `video/Kaskad_Video/<посёлок>.mp4`. Создайте статический ключ доступа.
2. **Backend**: соберите Docker-образ, положите модель `model/` и
   `data/feature_names.txt`, задайте env (S3 + `BACKEND_URL`), задеплойте
   в Yandex Serverless Container. См. [`backend/README.md`](backend/README.md)
   и `backend/deploy.sh`.
3. **Frontend**: задеплойте на Streamlit Cloud, задайте секрет `BACKEND_URL`.
   См. [`frontend/README.md`](frontend/README.md).

## Основные настройки окружения (backend)

| Переменная | Значение |
|------------|----------|
| `YC_S3_ENDPOINT` | `https://storage.yandexcloud.net` |
| `BUCKET_NAME` | имя бакета |
| `YC_ACCESS_KEY_ID` | статический ключ доступа |
| `YC_SECRET_ACCESS_KEY` | секрет ключа |
| `MODEL_PATH` | `model/global_best_model.joblib` |
| `FEATURE_NAMES_PATH` | `data/feature_names.txt` |
| `METRICS_S3_PREFIX` | `metrics/` (бэкап метрик) |

---

## Production-стандарты (что добавлено на практике 2)

### Poetry и виртуальное окружение

Зависимости всех компонентов (frontend + backend ML-стек + dev-инструменты)
живут в **одном pyproject.toml**; версии зафиксированы в `poetry.lock`.
ML-стек специально заперт на `numpy<2` + `scikit-learn==1.5.2`
(см. комментарии в pyproject) — это же связка задана в `backend/requirements.txt`
для Docker-образа, чтобы pickle-модель и локальный venv были совместимы.

```bash
# 1. Установка poetry (один раз)
pip install poetry

# 2. Скрипт создания окружения (отдельный py-скрипт в репозитории)
python scripts/run_poetry_setup.py    # poetry install --with dev

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
| `flake8` (pyflakes/pycodestyle/McCabe) | проверка на ошибки/PEP8/сложность кода |
| pre-commit-hooks | trailing-whitespace, EOF, check-yaml/toml, merge-conflict |

Отдельные скрипты (в репозитории, как требуется в ДЗ):

```bash
python scripts/run_black.py       # автоформатирование Black
python scripts/run_flake8.py      # линтер Flake8 (PEP8 + сложность McCabe)
python scripts/run_poetry_setup.py # создание/обновление poetry-окружения
```

Конфигурации — в `pyproject.toml` (секции `[tool.black]`, `[tool.isort]`,
`[tool.ruff]`, `[tool.mypy]`), сам Flake8 — в `.flake8`, хуки — в
`.pre-commit-config.yaml`.

### CI (GitHub Actions)

- `lint.yml` — ruff + `black --check` + `isort --check` на poetry-окружении;
- `tests.yml` — poetry install → `pytest -m "not api"` → live api-тесты при
  наличии секрета `BACKEND_URL`;
- `backend-deploy.yml`, `keep-warm.yml` — деплой в Yandex Cloud.

### Как просчитывалась жизнь проекта (сводка настроек)

| Файл | Роль |
|---|---|
| `pyproject.toml` | все зависимости + DEV-группа + config форматтеров/линтеров/pytest |
| `poetry.lock` | резолв версий (воспроизводимость окружения) |
| `.pre-commit-config.yaml` | хуки качества на каждый коммит |
| `.flake8` | Flake8: PEP8 + max-complexity (McCabe) |
| `scripts/run_*.py` | отдельные py-скрипты: Black / Flake8 / poetry-setup |
| `.gitattributes` | единые LF для скриптов/Dockerfile |
| `.gitignore` | исключает .venv, секреты, mp4-медиа, выгрузки метрик |
