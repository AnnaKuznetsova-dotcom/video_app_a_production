"""
tools/report_factor_csv.py — отчёт «Фактор / Вклад SHAP / Длительность».

Подписи брались из бэкенда video_app_a: POST /generate/ возвращает поле
factor_report (фактор -> вклад SHAP и длительность, пропорциональная вкладу).
Записываем CSV в tools/charts/factor_report.csv (бакет/модель/алгоритм не трогаем).

Запуск:
    BACKEND_URL=https://bbaev0p5a3rkd0ps3d4t.containers.yandexcloud.net \
    python tools/report_factor_csv.py
"""

import csv
import os
import sys

import requests

BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")
OUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts", "factor_report.csv")
HEADER = ["factor", "shap_value", "duration_s"]


def main() -> int:
    if not BACKEND_URL:
        print("Задайте BACKEND_URL (env). Пример: https://<container>.containers.yandexcloud.net")
        return 1
    features = {}
    # минимальный payload: backend сам заменит недостающие признаки нулями
    for name in sys.argv[1:]:
        k, _, v = name.partition("=")
        features[k] = int(v)
    resp = requests.post(
        f"{BACKEND_URL}/generate/",
        json={"features": features, "explicit_factors": []},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    rows = [
        {
            "factor": fr.get("factor", ""),
            "shap_value": fr.get("shap_value"),
            "duration_s": fr.get("duration_s"),
        }
        for fr in (data.get("factor_report") or [])
    ]
    if not rows:
        print("factor_report пустой для данного вектора (нет выбранных вариантов).")
        return 0
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    new_file = not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0
    with open(OUT_CSV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if new_file:
            w.writeheader()
        w.writerows(rows)
    print(f"OK -> {OUT_CSV} ({len(rows)} строк; settlement={data.get('settlement')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
