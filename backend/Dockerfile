# ---------- Базовый образ ----------
FROM python:3.11-slim

# ---------- Устанавливаем ffmpeg (ОБЯЗАТЕЛЬНО для moviepy/склейки видео) ----------
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Ставим зависимости (сначала только requirements — кеш слоя) ----------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------- Копируем модели и данные ----------
# Положите сюда свои .joblib-файлы:
#   backend/model/global_best_model.joblib
#   backend/model/xgb_explainer.joblib
#   backend/data/feature_names.txt
COPY model/ ./model/
COPY data/ ./data/

# ---------- Копируем код ----------
COPY main.py .
COPY metrics.py .
COPY video_api/ ./video_api/

# ---------- Запуск ----------
# Yandex Serverless Container ожидает, что приложение слушает порт 8080
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
