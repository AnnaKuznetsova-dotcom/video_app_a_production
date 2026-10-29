# Автотесты метрик: что нужно сделать со своей стороны

Это инструкция, какие автотесты можно запустить **бесплатно и автоматически**,
какие — только вручную, и **как разобрать уже собранные CSV-файлы метрик**.

---

## 0. Автоматический тестовый набор (pytest) — уже в репозитории

В папке `tests/` лежит готовый набор pytest:

| Файл | Что проверяет | Требуется сеть? |
|---|---|---|
| `test_frontend_units.py` | `validate_phone`, `area_to_rank`, границы сегментов, Spearman ρ | нет |
| `test_backend_api.py` | `/health`, `/predict`, `/metrics`, `/generate/`, невалидный payload | да (задеплоенный backend) |

**Запуск локально:**
```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -m "not api" -q   # только быстрые юнит-тесты
python -m pytest tests/ -q                # все, включая живые API-тесты
```

**В CI (GitHub Actions):** workflow `tests.yml` запускается на каждый push в `main`
(юнит-тесты всегда, API-тесты — если задан secret `BACKEND_URL`).

---

## 0. Короткий ответ: какие метрики тестируются автоматически, какие нет

| Метрика | Статус | Что можно сделать автотестом |
|---|---|---|
| **CTR превью** | 🟢 авто | Открыть страницу + нажать «Смотреть видео» → посчитать по `events.csv` |
| **CR (конверсия)** | 🟢 авто | Отправить форму заявки → посчитать по `events.csv` |
| **VCR (досмотры)** | 🟢 авто (новый плеер) | Досмотреть ролик до конца → считать `video_completed` |
| **TTL** | 🟢 авто | Сопоставить `lead_submit` и первую сессию по одному Client ID |
| **DFP** | 🟢 авто | Бэкенд сам считает в `summary.csv` |
| **High-Confidence** | 🟢 авто | Бэкенд сам считает в `summary.csv` |
| **Hit Ratio Top-3** | 🟢 авто (новое) | Бэкенд сам считает в `summary.csv` (признак == макс SHAP в группе) |
| **Render Latency** | 🟢 авто | Бэкенд сам пишет `total_ms`/`render_ms` |
| **Error Rate API** | 🟢 авто | Бэкенд сам считает `error_rate_pct_rounded_2` |
| **Cost per Inference** | 🟢 авто | Бэкенд сам считает `est_cost_per_inference_usd` |
| **Spearman ρ** | 🟢 авто | Плеер пишет `video_segment_watch` (время по сегментам). Стандартные длительности дают границы. `tools/view_metrics.py` считает ρ по рангам SHAP и времени просмотра |
| **Accuracy классификатора** | 🔴 ручной | Нужен размеченный тест-сет «вектор → реальный класс» |
| **QAR / артефакты ролика** | 🔴 ручной | Нужна ручная/MTurk-проверка роликов |

---

## 1. Что сделать со своей стороны, чтобы «накопить» данные для автотестов

1. **Прогнать сценарий реального пользователя** (хотя бы 5–10 раз):
   - открыть страницу KASKAD (это создаст сессии),
   - пройти анкету, нажать «Поиск идеального объекта»,
   - когда ролик готов — **досмотреть его до конца** (это даст `video_play` и
     `video_completed`; без досмотра VCR не посчитается),
   - заполнить форму «Заказать звонок» (это даст `lead_submit` для CR и TTL).

2. **Ничего дополнительно настраивать не нужно** — все цифры собираются кодом
   автоматически.

---

## 2. Где скачать собранные метрики

### 2.1. Frontend-метрики (CTR, CR, VCR, TTL)
Лежат прямо в Streamlit Cloud. Способа скачать их через веб-интерфейс нет,
поэтому **скачиваем через репозиторий/локально**:
- файлы создаются в папке `frontend/analytics_output/` при запуске приложения:
  - `sessions.csv` — каждый визит + Client ID,
  - `events.csv` — каждое событие (`preview_click`, `video_play`,
    `video_completed`, `lead_submit`, `latency_record`).

**Как получить их из Streamlit Cloud:** самый простой путь — запустить
`frontend/app.py` локально на своей машине (`streamlit run app.py`), пройти тот же
сценарий, и файлы появятся в `frontend/analytics_output/`. Либо настроить вывод
CSV в объектное хранилище (по аналогии с backend-метриками, см. ниже).

### 2.2. Backend-метрики (Latency, Error Rate, Cost, DFP, Hit Ratio, High-Confidence)
Бэкенд **автоматически выгружает** их в Yandex Object Storage, папка
`metrics/` внутри бакета `kuzenka-video-assets-2026`:
- `metrics/metrics.csv` — построчно каждый инференс,
- `metrics/metrics.csv` + `metrics/summary.csv` — сводка.

**Скачать одним запросом напрямую из браузера/curl:**
```
# Сводка (JSON, самая полезная — все агрегаты в одном месте)
curl https://bbaev0p5a3rkd0ps3d4t.containers.yandexcloud.net/metrics

# Сами CSV — из S3 (нужны ключи доступа, которыми настроен бэкенд):
#   aws s3 cp s3://kuzenka-video-assets-2026/metrics/metrics.csv .
#   aws s3 cp s3://kuzenka-video-assets-2026/metrics/summary.csv .
#   (или s3cmd, Cyberduck, консоль Yandex Cloud → Object Storage)
```

---

## 3. Python-код для анализа каждого CSV

### 3.1. Frontend: CTR, CR, VCR, TTL (`sessions.csv` + `events.csv`)
Запустите это и получите все бизнес-метрики на одной строке:

```python
import pandas as pd
from datetime import datetime

s = pd.read_csv("frontend/analytics_output/sessions.csv")
e = pd.read_csv("frontend/analytics_output/events.csv")

sessions = len(s)
plays    = (e["event_type"] == "video_play").sum()
comps    = (e["event_type"] == "video_completed").sum()
leads    = (e["event_type"] == "lead_submit").sum()

print("Сессий:", sessions)
print("CTR превью (%):", round(100*plays/sessions, 2) if sessions else None)
print("VCR (досмотры, %):", round(100*comps/plays, 2) if plays else None)
print("CR (конверсия в заявку, %):", round(100*leads/sessions, 2) if sessions else None)

# TTL: разница между первым заходом и лидом по одному Client ID
e["ts"] = pd.to_datetime(e["ts_iso"])
s["ts"] = pd.to_datetime(s["ts_iso"])
ttls = []
for cid in e.loc[e["event_type"]=="lead_submit","client_id"].unique():
    first = s.loc[s["client_id"]==cid,"ts"].min()
    last  = e.loc[(e["client_id"]==cid)&(e["event_type"]=="lead_submit"),"ts"].max()
    if pd.notna(first) and pd.notna(last):
        ttls.append((last-first).total_seconds())
print("TTL среднее (сек):", round(sum(ttls)/len(ttls),1) if ttls else None)
```

### 3.2. Frontend: латентность клиент→сервер (`events.csv`)
```python
import pandas as pd
e = pd.read_csv("frontend/analytics_output/events.csv")
lat = e.loc[e["event_type"]=="latency_record","extra"].str.extract(r"latency_ms=(\d+)").astype(float)
print("Latency avg п50 п95:", lat[0].mean(), lat[0].median(), lat[0].quantile(0.95))
```

### 3.3. Backend: всё техническое в одном месте (`summary.csv`)
```python
import pandas as pd
df = pd.read_csv("backend/data_metrics/summary.csv", names=["metric","value"])
print(df.to_string(index=False))
```
Увидите: `total_inferences`, `success`, `errors`, `error_rate_pct_rounded_2`,
`latency_ms_avg/p50/p95`, `render_ms_avg/p95`, `download_ms_avg`,
`dominant_feature_precision_dfp`, `share_high_confidence_predictions`,
`hit_ratio_top3_factors`, `groups_unique_rate`, `groups_duplicate_inferences`,
`est_cost_per_inference_usd`, `est_cost_usd_total`.

**Проверка дублей групп в ролике** (`groups_unique` в `metrics.csv`,
`groups_unique_rate` / `groups_duplicate_inferences` в сводке):
правило — один общий вид + **один клип на каждую группу**
(планировка / приоритеты / отделка / дети). Если в `top_factors` одной записи
попались 2 признака одной группы (например `bin_num__отделка_white_box` и
`bin_num__отделка_missing`), это баг сборки. Подсчёт:
```python
import pandas as pd, json
df = pd.read_csv("backend/data_metrics/metrics.csv")
for _, r in df.iterrows():
    names = json.loads(r["top_factors"]) if isinstance(r["top_factors"], str) and r["top_factors"] else []
    print(r["ts_iso"], r.get("groups_unique"), names)
```

### 3.4. Backend: построчный разбор (`metrics.csv`)
```python
import pandas as pd, json
df = pd.read_csv("backend/data_metrics/metrics.csv")
print(df.columns.tolist())
# Сколько было ошибок (success=0)
print("Ошибок:", (df["success"]==0).sum())
# Топ-SHAP-факторы по каждому инференсу:
df["top_factors"] = df["top_factors"].apply(lambda x: json.loads(x) if isinstance(x,str) and x else [])
for i,r in df.iterrows():
    print(r["ts_iso"], "| class", r["klass"], "|", r["settlement"], "|", r["total_ms"],"ms")
    print("   top:", r["top_factors"])
```

---

## 4. Метрики, которые автотестом НЕ измеряются (и почему)

- **Accuracy** — нужен заранее размеченный набор «вектор признаков → реальный
  класс посёлка», затем сравнить предсказание модели с истинным классом
  (у вас такой тест-сет уже есть).
- **QAR / артефакты** — нужна ручная или MTurk-проверка N роликов на дефекты
  (у вас такая проверка уже сделана; впишите фактическое значение).

> **Spearman ρ** теперь считается **автоматически**: плеер пишет
> `video_segment_watch` (время просмотра по сегментам), стандартные длительности
> сегментов дают границы, а `tools/view_metrics.py` вычисляет ρ по рангам SHAP
> и времени просмотра.

---

## 5. Порядок действий (чек-лист)

1. Открыть страницу KASKAD и пройти сценарий покупателя (5–10 раз), **досматривая
   каждый ролик до конца**.
2. Скачать сводку бэкенда: `curl https://<BACKEND_URL>/metrics`.
3. Скачать CSV из S3 (если нужен построчный разбор): `metrics/metrics.csv`,
   `metrics/summary.csv`.
4. Для frontend-метрик — запустить приложение локально или выгрузить
   `analytics_output/`, затем применить код из раздела 3.
5. Прогнать код из разделов 3.1–3.4 и собрать итоговые цифры.
6. Для метрик Spearman / Accuracy / QAR — сначала создать источник данных
   (см. раздел 4), автотест для них не применим до этого.
