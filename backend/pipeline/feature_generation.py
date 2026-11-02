"""Этап 2 — Feature generation: пространство признаков модели.

Здесь описано, ИЗ ЧЕГО состоит вектор признаков анкеты покупателя: смысловые
группы, префиксы one-hot колонок и проверка вектора на полноту/лишние ключи.

Замечание о разделении потоков: правило «ответ-в-анкете → колонка вектора»
(QUESTIONNAIRE_MAP, обнуление группы, перенос между группами, ранг площади)
живёт на стороне Streamlit в `frontend/videoapp/features.py` — там собирается
UI. Этот модуль хранит КОНТРАКТ той сборки, чтобы backend мог:
  1) валидировать вход (/generate получает полный вектор),
  2) документировать состав признаков в model_card.md без дублирования.
"""

import os

FEATURE_GROUPS = [
    {
        "key": "flat_plan",
        "label": "Планировка",
        "prefixes": ["bin_num__квартира_планировка", "few_cat__количество_комнат"],
        "columns_prefix": "bin_num__квартира_планировка",
    },
    {
        "key": "priorities",
        "label": "Приоритеты",
        "prefixes": ["bin_num__приоритеты"],
        "columns_prefix": "bin_num__приоритеты",
    },
    {
        "key": "finishing",
        "label": "Отделка",
        "prefixes": ["bin_num__отделка"],
        "columns_prefix": "bin_num__отделка",
    },
    {
        "key": "purchase_goal",
        "label": "Цель приобретения",
        "prefixes": ["bin_num__цель_приобретения"],
        "columns_prefix": "bin_num__цель_приобретения",
    },
    {
        "key": "payment_preference",
        "label": "Как бы предпочли купить",
        "prefixes": ["bin_num__как_бы_предпочли_купить_жилье"],
        "columns_prefix": "bin_num__как_бы_предпочли_купить_жилье",
    },
    {
        "key": "payment_scheme",
        "label": "Схема оплаты",
        "prefixes": ["bin_num__схема"],
        "columns_prefix": "bin_num__схема",
    },
    {
        "key": "area_rank",
        "label": "Площадь (ранг)",
        "prefixes": ["ord__ранг_площади"],
        "columns_prefix": "ord__ранг_площади",
    },
    {
        "key": "family",
        "label": "Семейное положение / авто",
        "prefixes": ["few_cat__семейное_положение", "few_cat__наличие_автомобиля"],
        "columns_prefix": "few_cat__",
    },
    {
        "key": "children",
        "label": "Дети",
        "prefixes": ["few_cat__есть_ли_дети"],
        "columns_prefix": "few_cat__есть_ли_дети",
    },
]


def _feature_names_static() -> list[str]:
    """Список признаков из backend/data/feature_names.txt (локальный файл repo)."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "feature_names.txt"
    )
    try:
        with open(path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []


def validate_feature_dict(features: dict) -> dict:
    """Валидация вектора признаков из запроса /generate.

    Возвращает отчёт::

        {
          "known_keys":  [...],   # ключи, входящие в пространство модели
          "unknown_keys": [...],  # лишние ключи (не влияют на предсказание,
                                  # т.к. DataFrame строится строго по колонкам модели)
          "groups_covered": {...} # по каждой группе: есть ли хоть один ненулевой
                                  # признак (иначе — колонка группы останется 0/missing)
        }
    """
    names = os.environ.get("FEATURE_NAMES_FALLBACK") and [] or _feature_names_static()
    known = set(names)
    keys = list(features.keys())
    unknown = [k for k in keys if k not in known]

    groups_covered = {}
    for grp in FEATURE_GROUPS:
        hit = any(
            str(k).startswith(prefix) and (features.get(k) or 0) != 0
            for prefix in grp["prefixes"]
            for k in keys
        )
        groups_covered[grp["key"]] = hit
    return {
        "known_keys": sorted(known & set(keys)),
        "unknown_keys": unknown,
        "groups_covered": groups_covered,
    }
