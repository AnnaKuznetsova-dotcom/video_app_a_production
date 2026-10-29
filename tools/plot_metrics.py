"""Построение backend-графиков в tools/charts/.

По умолчанию читает локальные метрики:
    backend/data_metrics/metrics.csv
    backend/data_metrics/summary.csv

Если передан аргумент — используется как путь к metrics.csv.
Если локальных файлов нет и аргумент не задан — пытается скачать CSV из S3.

Сохраняет копии сырых данных в tools/charts/:
    _metrics_raw.csv
    _summary_raw.csv

Сохраняет PNG-графики в tools/charts/.
"""

import os
import shutil
import sys

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

rcParams["font.family"] = "DejaVu Sans"
rcParams["axes.unicode_minus"] = False

S3_URL = "https://storage.yandexcloud.net/kuzenka-video-assets-2026/metrics/metrics.csv"
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(TOOLS_DIR, "charts")
PROJECT_ROOT = os.path.dirname(TOOLS_DIR)
LOCAL_METRICS = os.path.join(PROJECT_ROOT, "backend", "data_metrics", "metrics.csv")
LOCAL_SUMMARY = os.path.join(PROJECT_ROOT, "backend", "data_metrics", "summary.csv")


def _download(url: str, dst: str) -> str:
    import urllib.request

    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    urllib.request.urlretrieve(url, dst)
    return dst


def _copy_or_download(src: str, dst: str, fallback_url: str) -> str:
    if src and os.path.exists(src) and os.path.getsize(src) > 0:
        shutil.copy2(src, dst)
        return src
    print(f"Локальный файл не найден: {src}; скачиваем из {fallback_url}")
    return _download(fallback_url, dst)


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def main():
    import csv as _csv

    os.makedirs(CHARTS_DIR, exist_ok=True)

    raw_dst = os.path.join(CHARTS_DIR, "_metrics_raw.csv")
    summary_dst = os.path.join(CHARTS_DIR, "_summary_raw.csv")

    # --- источник metrics.csv ---
    if len(sys.argv) > 1:
        src = sys.argv[1]
        shutil.copy2(src, raw_dst)
    else:
        src = _copy_or_download(LOCAL_METRICS, raw_dst, S3_URL)

    # --- копия summary.csv ---
    if os.path.exists(LOCAL_SUMMARY):
        shutil.copy2(LOCAL_SUMMARY, summary_dst)

    # Схема v4 (20 колонок). Старые строки с меньшим числом полей — через fallback.
    BASE = [
        "ts_iso",
        "endpoint",
        "settlement",
        "klass",
        "top_factors",
        "fragments_used",
        "download_ms",
        "render_ms",
        "total_ms",
    ]
    EXTRA = [
        "shap_mismatch_groups",
        "success",
        "error",
        "groups_unique",
        "latency_ms",
        "variant",
        "preprocess_ms",
        "predict_ms",
        "shap_ms",
        "model_load_ms",
        "is_cold",
    ]

    def _map_row(ln):
        d = dict(zip(BASE, ln[:9], strict=False))
        for i, col in enumerate(EXTRA):
            idx = 9 + i
            d[col] = ln[idx] if len(ln) > idx else ""
        return d

    records = []
    with open(src, encoding="utf-8-sig", newline="") as f:
        rdr = _csv.reader(f)
        next(rdr, None)  # заголовок игнорируем — схема строки надёжнее
        for cells in rdr:
            if not cells or (len(cells) == 1 and not cells[0].strip()):
                continue
            records.append(_map_row(cells))
    df = pd.DataFrame(records)
    df["ts_iso"] = df["ts_iso"].astype(str).str.slice(0, 19)
    df["success"] = df["success"].astype(str).str.strip()
    df["groups_unique"] = df["groups_unique"].astype(str).str.strip()
    ok = df[df["success"] == "1"].copy()
    bad = df[df["success"] != "1"]
    print(f"Всего запросов: {len(df)} | успешных: {len(ok)} | неуспешных: {len(bad)}")
    if ok.empty:
        print("Нет успешных инференсов — графиков нет.")
        return

    numeric_cols = [
        "download_ms",
        "render_ms",
        "total_ms",
        "latency_ms",
        "preprocess_ms",
        "predict_ms",
        "shap_ms",
        "model_load_ms",
    ]
    for col in numeric_cols:
        if col in ok.columns:
            ok[col] = pd.to_numeric(ok[col], errors="coerce")

    # Печать базовой статистики
    for col in (
        "total_ms",
        "latency_ms",
        "preprocess_ms",
        "predict_ms",
        "shap_ms",
        "model_load_ms",
    ):
        if col not in ok.columns:
            continue
        s = ok[col].dropna()
        if s.empty:
            continue
        print(
            f"{col}: avg={s.mean():.0f}ms p50={s.median():.0f}ms p95={s.quantile(0.95):.0f}ms max={s.max():.0f}ms"
        )

    # 1. Временной ряд latency
    ok_t = ok.sort_values("ts_iso")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(
        range(len(ok_t)),
        ok_t["total_ms"].astype(float),
        marker="o",
        markersize=3,
        label="total, ms",
    )
    if "latency_ms" in ok_t.columns and ok_t["latency_ms"].notna().any():
        ax.plot(
            range(len(ok_t)),
            ok_t["latency_ms"].astype(float),
            marker="x",
            linestyle="--",
            label="client latency, ms",
        )
    ax.set_xticks(range(len(ok_t)))
    ax.set_xticklabels([str(x)[11:16] for x in ok_t["ts_iso"]], rotation=90, fontsize=7)
    ax.set_title("Latency по инференсам")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/latency_timeline.png", dpi=120)
    plt.close(fig)

    # 2. Распределение total latency (гистограмма)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(ok["total_ms"].astype(float) / 1000.0, bins=20, edgecolor="white")
    ax.set_xlabel("total, сек")
    ax.set_title("Распределение времени генерации")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/latency_hist.png", dpi=120)
    plt.close(fig)

    # 3. Cоотношение render vs download
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.scatter(ok["download_ms"].astype(float), ok["render_ms"].astype(float), alpha=0.6)
    ax.set_xlabel("download_ms")
    ax.set_ylabel("render_ms")
    ax.set_title("Download vs Render (мс)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{CHARTS_DIR}/download_vs_render.png", dpi=120)
    plt.close(fig)

    # 4. Сегментация по классам
    if "settlement" in ok:
        cnt = ok["settlement"].value_counts()
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(cnt.index, cnt.values, color="forestgreen")
        ax.set_title("Генерации по посёлкам (класс)")
        ax.grid(alpha=0.3, axis="y")
        fig.tight_layout()
        fig.savefig(f"{CHARTS_DIR}/by_settlement.png", dpi=120)
        plt.close(fig)

    # 5. Этапы хронометража (warm p50) — из summary.csv
    if os.path.exists(summary_dst):
        try:
            summary_df = pd.read_csv(summary_dst, encoding="utf-8-sig")
            summary = dict(
                zip(summary_df["metric"].astype(str), summary_df["value"].astype(str), strict=False)
            )
            stage_keys = [k for k in summary if k.startswith("stage_") and k.endswith("_p50_warm")]
            if stage_keys:
                stage_data = []
                for k in sorted(stage_keys):
                    v = _num(summary[k])
                    if v is not None:
                        stage_data.append(
                            {
                                "этап": k.replace("stage_", "").replace("_ms_p50_warm", ""),
                                "мс": v,
                            }
                        )
                if stage_data:
                    sdf = pd.DataFrame(stage_data)
                    fig, ax = plt.subplots(figsize=(7, 4))
                    ax.barh(sdf["этап"], sdf["мс"], color="steelblue")
                    ax.set_xlabel("мс")
                    ax.set_title("Хронометраж этапов (warm, p50)")
                    ax.grid(alpha=0.3, axis="x")
                    fig.tight_layout()
                    fig.savefig(f"{CHARTS_DIR}/stage_timing.png", dpi=120)
                    plt.close(fig)
        except Exception as e:
            print("Не удалось построить график этапов:", e)

    print(f"\nГрафики сохранены в: {CHARTS_DIR}")
    print(sorted(os.listdir(CHARTS_DIR)))


if __name__ == "__main__":
    main()
