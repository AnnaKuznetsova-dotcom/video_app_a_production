# Этап 5 — контур обучения/обновления модели (model update)

Реализация шагов BPMN из [`Model_retrain_BPMN.md`](../../Model_retrain_BPMN.md).
Каждый файл = один шаг; данные передаются явными аргументами, чтобы шаги
можно было запускать и из cron, и вручную.

| Модуль | Шаг BPMN | Что происходит | Результат для следующего шага |
|---|---|---|---|
| `dataset_validation.py` | Проверка пригодности данных | пороги из §5 BPMN: пропуски > 10 %, дубли > 5 %, класс > 80 % | отчёт `{"ok", "failures"}`; отказ фиксируется в журнале аудита |
| `training.py` | Обучение кандидата | XGBClassifier, split 70/15/15, seed=42 | `candidate_model_vN.joblib` + метрики val/test |
| `evaluation.py` | Проверка качества | Accuracy не ниже baseline −3 п.п.; Recall macro не ниже −5 п.п. | решение `passes_thresholds` для этапа согласования |
| `promotion.py` | Регистрация версии | копия в реестр + новый baseline + переключение active-указателя + обновление `global_best_model.joblib` | зарегистрированная версия, готовая к деплою |

## Запуск (после востребования, при наличии датасета)

```bash
cd backend
# 1. Проверка данных + обучение кандидата
python -m pipeline.model_update.training --dataset data/dataset_vYYYYMMDD.csv
# 2. Сравнение с baseline (в коде; при успехе — на согласование бизнесу)
python - <<'PY'
from pipeline.model_update import evaluation, training
result = training.train_candidate("data/dataset_vYYYYMMDD.csv")
print(evaluation.passes_thresholds(result["metrics"]))
PY
# 3. После письменного утверждения бизнесом:
python - <<'PY'
from pipeline.model_update import promotion
print(promotion.promote_candidate("model/versions/model_vN.joblib",
      metrics={...}, approved_by="owner@kaskad"))
PY
```

Скелет сознательно не тянет MLflow/Airflow: единая точка входа в деплой —
GitHub Actions (`backend-deploy.yml`), а политики переходов расписаны в BPMN.
