# Backend — Yandex Serverless Container (FastAPI)

Сервис сборки персонального видео из фрагментов. Принимает от Streamlit полный
вектор признаков покупателя, предсказывает класс поселка, считает SHAP-факторы,
скачивает нужные ролики из Yandex Object Storage, склеивает их и возвращает
публичную ссылку на результат.

## Структура папки

```
backend/
├── Dockerfile           # образ с ffmpeg + модели + код
├── requirements.txt     # зависимости Python
├── main.py              # FastAPI-приложение
├── deploy.sh            # сборка + деплой через YC CLI
├── .env.example         # пример переменных окружения
├── model/               # ПОЛОЖИТЕ СВОИ .joblib-модели сюда
│   ├── global_best_model.joblib
│   └── xgb_explainer.joblib
└── data/
    └── feature_names.txt  # (опционально) имена признаков по строкам
```

## Эндпоинты

| Метод | Путь        | Описание                                            |
|-------|-------------|-----------------------------------------------------|
| GET   | `/health`   | проверка живости и наличия моделей                   |
| POST  | `/predict`  | класс + топ-факторы SHAP (без сборки видео)          |
| POST  | `/generate/`| полный конвейер: класс → SHAP → сборка → ссылка      |

### Пример запроса `POST /generate/`

```json
{
  "features": {
    "bin_num__квартира_планировка_1_комн": 0,
    "bin_num__квартира_планировка_2_комн": 1,
    "bin_num__приоритеты_инфраструктура": 1,
    "fetch_cat__есть_ли_дети_Есть": 1,
    "...": 0
  },
  "explicit_factors": []
}
```

`features` — это полный DataFrame с одной строкой, преобразованный в dict.

### Ответ `POST /generate/`

```json
{
  "video_url": "https://<bucket>.storage.yandexcloud.net/outputs/user_video_<uuid>.mp4",
  "job_id": "...",
  "settlement": "Akademia_Park",
  "klass": 1,
  "used_factors": ["bin_num__приоритеты_инфраструктура", "..."],
  "ranked_factors": ["..."]
}
```

## Локальный запуск для отладки

```bash
pip install -r requirements.txt
# положите модели в model/ и data/
set BUCKET_NAME=...   # PowerShell
set YC_ACCESS_KEY_ID=...
set YC_SECRET_ACCESS_KEY=...
uvicorn main:app --reload --port 8080
```

## Как собрать и задеплоить

1. Соберите образ с ffmpeg и моделями (см. `Dockerfile`).
2. Загрузите модели в `model/` и `data/`.
3. Запустите `bash deploy.sh` (заполнив переменные) либо деплойте через
   Yandex Cloud Console → Serverless Containers.
4. Укажите переменные окружения (см. `.env.example`).

> ВАЖНО: названия папок видео на S3 см. в `main.py` (`VIDEO_PATH_MAP`).
> Код устойчив к именам файлов `video1.mp4` / `video.mp4` и к опечаткам в папках
> (`proirities`, `priotrities` и т.п.) — он ищет первый `.mp4` в нужной подпапке.

## Метрики (технические)

Backend автоматически пишет каждый инференс в `data_metrics/metrics.csv`
(latency, render time, download time, error rate, класс, топ-SHAP-факторы,
стоимость CPU) и сводку в `data_metrics/summary.csv`. Смотреть без SQL:

```bash
python tools/view_metrics.py             # сводный отчёт
# или
python -c "import pandas as pd; print(pd.read_csv('data_metrics/summary.csv'))"
```

Эндпоинт `GET /metrics` отдаёт сводку JSON. Подробнее — в корневом `METRICS.md`.

> ⚠️ Файловая система Serverless Container эфемерна. Чтобы метрики не исчезали
> после рестарта, backend **автоматически** синхронизирует их с S3 (папка
> `metrics/`): при старте скачивает накопленный CSV, после каждого инференса
> загружает обратно. Для этого достаточно тех же S3-переменных, что и для видео
> (префикс — `METRICS_S3_PREFIX`, по умолчанию `metrics/`). Если S3 не задан —
> метрики живут только локально.
