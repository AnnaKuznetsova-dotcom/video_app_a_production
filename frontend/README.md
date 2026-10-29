# Frontend — Streamlit (персональный AI-куратор видео)

Интерфейс, который задаёт покупателю вопросы, собирает вектор признаков и
отправляет его в Backend (Yandex Serverless Container), а затем показывает
готовый персональный ролик.

## Структура папки

```
frontend/
├── app.py                    # основное Streamlit-приложение
├── requirements.txt          # зависимости
├── .streamlit/
│   ├── config.toml           # премиум-тема (тёмная, золото)
│   └── secrets.toml.example  # пример секретов (BACKEND_URL)
└── data/
    └── feature_names.txt     # ВАЖНО: имена фич модели (одна колонка в строке)
```

## Локальный запуск

```bash
pip install -r requirements.txt

# 1) положите feature_names.txt в frontend/data/
# 2) задайте адрес бэкенда
set BACKEND_URL=http://localhost:8080   # PowerShell

streamlit run app.py
```

## Как это работает

1. Покупатель отвечает на вопросы анкеты (планировка, приоритеты, отделка,
   наличие детей, семья, авто, площадь).
2. `build_feature_vector()` собирает полный вектор признаков — точно так же,
   как в блокноте (обнуление группы, простановка единиц, перенос между
   группами, перевод площади в ранг).
3. Приложение отправляет `POST /generate/` в Backend с `{"features": {...}}`.
4. Backend предсказывает посёлок, считает SHAP, склеивает ролик из кусков
   на Yandex Object Storage и возвращает публичную ссылку.
5. Streamlit отображает готовый ролик.

## Деплой на Streamlit Community Cloud

1. Запушьте репозиторий `frontend` на GitHub.
2. В Streamlit Cloud → New app → выберите репозиторий и файл `app.py`.
3. В Settings → Secrets добавьте:
   ```toml
   BACKEND_URL = "https://<url-serverless-container>"
   ```
4. Deploy. Приложение будет доступно по публичной ссылке Streamlit.

> Совет: если в Streamlit Cloud нельзя держать `data/feature_names.txt` слишком
> большим — он небольшой, так что это не проблема. Главное, чтобы он совпадал
> со списком фич модели в Backend.

## Метрики (бизнесовые)

Frontend собирает события в `analytics_output/`:
- `sessions.csv` — каждый заход (Client ID в cookie `tlx_client_id`).
- `events.csv` — клики «Смотреть видео» (`preview_click`), лиды
  «Заказать звонок» (`lead_submit`), замер latency (`latency_record`).

По ним считаются **CTR**, **конверсия в лид (CR)** и **Time-to-Lead**:

```bash
python tools/view_metrics.py
```

Кнопки «Смотреть видео» и форма «Заказать звонок» уже добавлены в `app.py`.
Подробно — в корневом `METRICS.md` (там же — как открыть консоль разработчика).
