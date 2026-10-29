# Инструменты анализа метрик (tools/)

Скрипты для работы с CSV-метриками, собранными приложением. Не требуют SQL —
всё читается pandas/CSV.

```
tools/
├── metrics_core.py                  # общая логика: загрузка CSV, расчёт группы Б, ввод группы А
├── report_metrics.py                # отчёт в терминал + PNG-графики (plotly)
├── report_metrics_html.py           # интерактивный HTML-отчёт (таблицы + plotly)
├── view_metrics.py                  # быстрая сводка технических + бизнес-метрик (без ввода группы А)
├── fetch_electric_schedule.py       # выкачка расписания электричек (Яндекс Расписания v3)
└── requirements.txt                 # pandas, plotly, kaleido, requests
```

## Установка зависимостей

```bash
pip install -r tools/requirements.txt
```

## 1. Быстрый отчёт (терминал + PNG-графики)

```bash
python tools/report_metrics.py [путь_к_проекту]
```

- Читает реальные метрики **Группы Б (AI)** из CSV.
- Через `input()` спрашивает данные **Группы А (контроль)** (можно пропустить поле
  нажатием Enter).
- Строит графики plotly и сохраняет PNG в `reports/`.
- Печатает «Сводную таблицу метрик».

## 2. Интерактивный HTML-отчёт

```bash
python tools/report_metrics_html.py [путь_к_проекту]
```

Создаёт `reports/report.html` (гипотеза, карточки КPI, сводная таблица,
интерактивные графики) и открывает в браузере.

## 3. Отчёт в pandas (для jupyter/исследований)

```python
import sys; sys.path.insert(0, "tools")
import metrics_core as mc

root = mc.locate_project()
dfs = mc.load_dataframes(root)          # {"events": df, "sessions": df, "backend": df, "summary": df}
events = dfs["events"]
print(events.head())

b = mc.load_group_b(root)               # рассчитанные метрики группы Б
print(b["cr_pct"], b["ttl_hours"])
```

## Что считается автоматически из CSV

| Метрика | Источник |
|---------|----------|
| CR / CTR / Time-to-Lead | `frontend/analytics_output/sessions.csv` + `events.csv` |
| Latency (P95/avg) | `events.csv` (событие `latency_record`) |
| Error Rate, число инференсов | `backend/data_metrics/metrics.csv` |

## Что вводится вручную (не собирается из CSV)

- **VCR** — нужен видеоплеер с событиями (в Streamlit `st.video` их нет).
- **Accuracy** — нужна CRM-разметка реальных сделок.
- **Hit Ratio топ-3** — нужны отзывы покупателей после сделки.

Эти три значения запрашиваются через `input()` при запуске отчёта.

## 4. Расписание пригородных электричек (Яндекс Расписания)

Скрипт `fetch_electric_schedule.py` выкачивает **все остановки** рейсов
(ниток) пригородных электричек Москвы и Московской области: для каждого
поезда — станцию, время прибытия и отправления на каждой остановке
(а не только первую и последнюю).

Нужен бесплатный API-ключ «Яндекс Расписания» (developer.tech.yandex.ru →
«Яндекс Расписания», лимиты ~10 RPS и суточная норма запросов). Ключ
передаётся через `RASP_API` или `--api-key`.

```bash
set RASP_API=<ваш_ключ>          # Windows (или export RASP_API=... в Linux/macOS)
pip install requests
python tools/fetch_electric_schedule.py --days 7
```

Опции: `--start 2026-09-20` (первый день), `--days N`, `--year 2026` (весь год
с 1 января), `--max-requests N` (стоп после N запросов в запуск), `--out
<файл.csv>`, `--limit-stations N` (быстрая проверка), `--sleep <сек>` (пауза
между запросами).

Год целиком не выкачивается за один день: у API суточный лимит. Запускайте
порциями — скрипт продолжает с места:

```bash
python tools/fetch_electric_schedule.py --year 2026 --max-requests 5000
```

Порядок работы скрипта:
1. `stations_list` (полный дамп ~34 МБ: страны → регионы → населённые пункты →
   станции; берутся ж/д станции региона «Москва и Московская область» —
   транспортные типы `train`/`suburban`).
2. `schedule` по каждой станции и дате (пагинация через `offset`) — список
   ниток (uid рейсов), проходящих станцию.
3. `thread` по каждой уникальной нитке (`uid`+дата) — `stops[]`, все станции
   следования с временами прибытия/отправления.

Повторный запуск продолжает с места — прогресс в файлах рядом с `--out`:
`<out>.enum.done.log` (`station_code|date` — расписание станции прочитано) и
`<out>.stops.done.log` (`thread_uid|date` — остановки нитки записаны).
При HTTP 429 (суточный лимит / «ключ не активен») парсер останавливается,
остаток докачивается при следующем запуске.

Выходные поля CSV (одна строка = одна остановка нитки):
`date, thread_uid, thread_number, thread_title, start_time,
transport_subtype_code, express_type, carrier_title, stop_order, stop_code,
stop_title, latitude, longitude, arrival, departure, stop_seconds, platform,
is_first, is_last`.

## Примечание

`report_metrics.py` при загрузке группы Б считает **уникальных пользователей**
по полю `client_id`. Если у одного посетителя несколько сессий, они не
задваиваются в знаменателе CR/CTR.
