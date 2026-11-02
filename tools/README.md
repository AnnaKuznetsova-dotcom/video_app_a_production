# Инструменты анализа метрик (tools/)

Скрипты для работы с CSV-метриками, собранными приложением. Не требуют SQL —
всё читается pandas/CSV.

```
tools/
├── metrics_core.py                  # общая логика: загрузка CSV, расчёт группы Б, ввод группы А
├── report_metrics.py                # отчёт в терминал + PNG-графики (plotly)
├── report_metrics_html.py           # интерактивный HTML-отчёт (таблицы + plotly)
├── view_metrics.py                  # быстрая сводка технических + бизнес-метрик
├── plot_metrics.py                  # PNG-графики из backend/data_metrics (matplotlib)
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

Эти значения запрашиваются через `input()` при запуске отчёта.

## Примечание

`report_metrics.py` при загрузке группы Б считает **уникальных пользователей**
по полю `client_id`. Если у одного посетителя несколько сессий, они не
задваиваются в знаменателе CR/CTR.
