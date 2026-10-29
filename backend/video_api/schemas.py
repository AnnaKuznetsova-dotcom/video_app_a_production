"""
Pydantic-схемы запросов и ответов Video API (вариант A).
"""

from typing import Any

from pydantic import BaseModel


class FeatureVectorPayload(BaseModel):
    """Полный вектор признаков покупателя (все колонки модели)."""

    features: dict[str, Any]
    # опционально: факторы, переданные Streamlit-ом в обход SHAP
    explicit_factors: list[str] = []
    # опционально: false — не писать этот вызов в метрики (для тестов и отладки)
    tracked: bool = True


class PredictResponse(BaseModel):
    klass: int
    settlement: str
    variant: str
    top_factors: list[str]
