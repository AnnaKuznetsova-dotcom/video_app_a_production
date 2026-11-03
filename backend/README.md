# Backend — Yandex Serverless Container (FastAPI)

Сервис подбора посёлка по ответам анкеты. Принимает от Streamlit полный вектор
признаков покупателя, предсказывает класс посёлка, отдаёт публичную ссылку на
**фиксированный ролик этого посёлка** (вариант A: ролик не зависит от
индивидуальных ответов — только от предсказанного класса).

## Конвейер по этапам (backend/pipeline/)

Код разбит на этапы ML-процесса — один файл = один этап, данные передаются
явно сверху вниз:

```
backend/
├── main.py                    # тонкая точка входа FastAPI (uvicorn main:app)
├── pipeline/                  # ML-конвейер
│   ├── config.py              # этап 0: env, S3, карты посёлок → ролик
│   ├── data_preprocessing.py  # этап 1: вектор из JSON → DataFrame модели
│   ├── feature_generation.py  # этап 2: контракт пространства признаков анкеты
│   ├── model_inference.py     # этап 3: загрузка joblib + predict посёлка
│   ├── model_registry.py      # этап 4: версии модели (versions/ + active_model.txt)
│   ├── model_update/          # этап 5: скелет переобучения (Model_retrain_BPMN.md)
│   │   ├── dataset_validation.py
│   │   ├── training.py
│   │   ├── evaluation.py
│   │   ├── promotion.py
│   │   └── README.md
│   ├── metrics_tracker.py     # этап 6: техметрики инференса (CSV + S3)
│   └── serving/routes.py      # этап 7: HTTP-эндпоинты
├── Dockerfile
├── requirements.txt
├── deploy.sh                  # сборка + деплой в YC
├── .env.example
├── model/                     # global_best_model.joblib (+ versions/, реестр)
├── data/
│   └── feature_names.txt      # имена фич (одна на строку)
└── media/                     # локальный режим: готовые ролики посёлков
```

## Эндпоинты

| Метод | Путь        | Описание                                            |
|-------|-------------|-----------------------------------------------------|
| GET   | `/health`   | проверка живости и наличия модели                    |
| POST  | `/predict`  | класс → посёлок → variant (без видео)                |
| POST  | `/generate/`| предсказание + ссылка на фиксированный ролик         |
| GET   | `/metrics`  | сводка технических метрик                            |
| POST  | `/admin/reset_metrics` | сброс метрик по токену METRICS_ADMIN_TOKEN |

### Пример запроса `POST /generate/`

```json
{
  "features": {
    "bin_num__квартира_планировка_1_комн": 0,
    "bin_num__квартира_планировка_2_комн": 1,
    "bin_num__приоритеты_инфраструктура": 1,
    "few_cat__есть_ли_дети_Есть": 1,
    "...": 0
  }
}
```

### Ответ `POST /generate/`

```json
{
  "video_url": "https://<bucket>.storage.yandexcloud.net/video/Kaskad_Video/<посёлок>.mp4",
  "job_id": "...",
  "settlement": "Akademia_Park",
  "klass": 1,
  "variant": "1_базовый_Akademia_Park",
  "stage_timing_ms": {"preprocess": 5, "predict": 12, "model_load": 400, "total": 900}
}
```

## Локальный запуск для отладки

```bash
pip install -r requirements.txt
# положите модель в model/ и data/
set BUCKET_NAME=...   # PowerShell
set YC_ACCESS_KEY_ID=...
set YC_SECRET_ACCESS_KEY=...
uvicorn main:app --reload --port 8080
```

## Как собрать и задеплоить

1. Соберите образ (см. `Dockerfile`).
2. Положите модель в `model/` и `data/`.
3. Запустите `bash deploy.sh` (заполнив переменные) либо деплойте через
   Yandex Cloud Console → Serverless Containers.
4. Укажите переменные окружения (см. `.env.example`).

## Метрики (технические)

Backend автоматически пишет каждый инференс в `data_metrics/metrics.csv`
(latency по стадиям preprocess/predict, cold/warm split, error rate,
стоимость CPU) и сводку в `data_metrics/summary.csv`. Смотреть без SQL:

```bash
python tools/view_metrics.py             # сводный отчёт
```

Эндпоинт `GET /metrics` отдаёт сводку JSON. Подробнее — в корневом `METRICS.md`.

> ⚠️ Файловая система Serverless Container эфемерна. Чтобы метрики не исчезали
> после рестарта, backend **автоматически** синхронизирует их с S3 (папка
> `metrics/`): при старте скачивает накопленный CSV, после каждого инференса
> загружает обратно. Для этого достаточно тех же S3-переменных, что и для видео
> (префикс — `METRICS_S3_PREFIX`, по умолчанию `metrics/`). Если S3 не задан —
> метрики живут только локально.

## Обновление модели (контур авто-пайплайна)

Процесс — в [`Model_retrain_BPMN.md`](../Model_retrain_BPMN.md), код — в
`backend/pipeline/model_update/` (валидация датасета → обучение кандидата →
проверка порогов → регистрация версии). **Штатно контур работает
автоматически**; человек подключается только при больших отклонениях
(провал порогов, деградация на карантине). Переобучение запускается, в том
числе, когда появляется **новый класс = новый посёлок/объект недвижимости** —
в этот режиме обязательно **ручные верификации**: нового датасета, обновлённого
`CLASS_MAP` и корректной контрольной выдачи до включения посёлка в продакшн
(без переобучения класс моделью не предсказывается).
