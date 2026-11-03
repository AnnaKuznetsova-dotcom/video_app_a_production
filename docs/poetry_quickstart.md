# Краткая справка: Poetry и виртуальное окружение

Poetry — менеджер зависимостей и виртуальных окружений: декларирует
зависимости в `pyproject.toml`, фиксирует точные версии в `poetry.lock` и
изолирует пакеты в `.venv`.

## 1. Основные этапы создания окружения — шаги и смысл

| Шаг | Команда | Что делает / смысл |
|---|---|---|
| **1. Установка Poetry** | `pip install poetry` | Ставится сам инструмент (глобально, вне проекта). Проверка: `poetry --version` |
| **2. Настройка окружения** | `poetry config virtualenvs.in-project true --local` | `.venv` создаётся в корне репозитория (в `.gitignore`) — удобно для локальной отладки и CI. В нашем проекте это зафиксировано в `poetry.toml` |
| **3. Декларация зависимостей** | редактирование `pyproject.toml` | `[tool.poetry.dependencies]` — рантайм; `[tool.poetry.group.dev.dependencies]` — dev-инструменты (pytest, black, flake8, isort, ruff, pre-commit). Разделение «прод-зависимостям не нужны тесты» |
| **4. Создание окружения и установка** | `poetry install` (или наш скрипт `python scripts/run_poetry_setup.py`) | Создаёт `.venv` и ставит пакеты **точно в версиях `poetry.lock`** — окружение воспроизводимое |
| **5. Работа внутри окружения** | `poetry run <cmd>` / `poetry shell` | Команда выполняется в изолированном окружении, ничего не засоряет системный Python |
| **6. Добавление/обновление пакетов** | `poetry add <pkg>`, `poetry add --group dev <pkg>`, `poetry update` | Обновляет `pyproject.toml` и пересчитывает `poetry.lock` |
| **7. Согласование версий Python** | `poetry env use python3.12` | Если заявлено `python >=3.12,<3.14` — Poetry не соберёт окружение на неподходящем Python |
| **8. Очистка/диагностика** | `poetry env info`, `poetry cache clear …` | Информация об окружении (Python, пути), сброс кеша пакетов |

## 2. Что идёт в git

| Файл | Роль | В git? |
|---|---|---|
| `pyproject.toml` | Декларативные зависимости + конфиги black/isort/ruff/mypy/pytest | ✅ да |
| `poetry.lock` | Полный резолвер версий (воспроизводимость) | ✅ да |
| `poetry.toml` | Локальные настройки Poetry (`virtualenvs.in-project` и др.) | ✅ да |
| `.venv/` | Само виртуальное окружение | ❌ нет (`.gitignore`) |

Итог: любой разработчик/CI с установленным Poetry получает байт-в-байт то же
окружение простым `poetry install`.

## 2.1. Что в проекте — «venv + poetry»? Это одно и то же, дублирования нет

`venv` в проекте — это **не отдельная система**, а то, что создаёт сам Poetry:
`virtualenvs.in-project = true` (файл `poetry.toml`) → `poetry install`
создаёт изолированное окружение `.venv/` в корне репозитория. Мы никогда не
делаем второй `python -m venv .venv` руками.

| Контекст | Инструмент | Зависимости | Почему так |
|---|---|---|---|
| Локальная разработка, CI (`lint.yml`, `tests.yml`), pre-commit | **Poetry** | `pyproject.toml` + `poetry.lock` (→ `.venv`) | воспроизводимость, dev-группа инструментов |
| Docker-образ backend (`Dockerfile`) | pip | `backend/requirements.txt` | poetry в минимальном контейнере не нужен, слой кешируется |
| Streamlit Community Cloud (frontend) | pip | `frontend/requirements.txt` | хостинг поддерживает **только requirements.txt** |
| Разовые скрипты `tools/` | pip | `tools/requirements.txt` | изолированный вспомогательный комплект |

`backend/requirements.txt` содержит те же ключевые пины (numpy<2,
scikit-learn==1.5.2, xgboost), что и `pyproject.toml` — так pickle-модель
в контейнере совместима байт-в-байт с локальным окружением. Это
специально поддерживаемое дублирование двух окружений (dev vs prod-образы),
а не два менеджера в одном окружении.

## 3. Специфика этого проекта

- Python заявлен как `>=3.12,<3.14` — при установленном новее (например 3.14)
  нужно переключить окружение: `poetry env use python3.12`.
- ML-стек заперт на `numpy<2` + `scikit-learn==1.5.2`; тот же стек задан в
  `backend/requirements.txt` для Docker-образа, чтобы pickle-модель была
  совместима байт-в-байт.
- Скрипт автоматизации ДЗ1: `python scripts/run_poetry_setup.py`
  (обёртка над `poetry install --with dev`).

## 4. Типовой сценарий ДЗ1 (сжатая инструкция)

```bash
# 1) установка Poetry (один раз)
pip install poetry
# 2) создать окружение и зависимости из lock-файла
python scripts/run_poetry_setup.py     # то есть poetry install --with dev
# 3) инструменты качества
poetry run pre-commit install
poetry run pre-commit run --all-files
# 4) тесты / запуск приложений
poetry run python -m pytest tests/ -m "not api" -q
poetry run streamlit run frontend/app.py
```
