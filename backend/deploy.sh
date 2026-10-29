#!/usr/bin/env bash
# Скрипт сборки и деплоя в Yandex Serverless Container.
#
# Требования:
#   - установлен Yandex Cloud CLI (yc) и авторизован
#   - создан реестр контейнеров (Container Registry) и задекларирован
#     Serverless Container
#
# Шаги (заполните переменные перед запуском):
#   export REGISTRY_ID=<id реестра>
#   export CONTAINER_ID=<id serverless-контейнера>
#   export SERVICE_ACCOUNT_ID=<id сервисного аккаунта с правами на Container Registry>
#   export BUCKET_NAME=<имя бакета>
#   export YC_ACCESS_KEY_ID=<статический ключ>
#   export YC_SECRET_ACCESS_KEY=<секрет>
#
# Затем:  bash deploy.sh

set -euo pipefail

REGISTRY_ID="${REGISTRY_ID:-}"
CONTAINER_ID="${CONTAINER_ID:-}"
SERVICE_ACCOUNT_ID="${SERVICE_ACCOUNT_ID:-}"
FOLDER_ID="${FOLDER_ID:-}"
IMAGE_NAME="video-assembler:latest"

if [[ -z "$REGISTRY_ID" || -z "$CONTAINER_ID" || -z "$SERVICE_ACCOUNT_ID" || -z "$FOLDER_ID" ]]; then
  echo "Заполните REGISTRY_ID, CONTAINER_ID, SERVICE_ACCOUNT_ID, FOLDER_ID" >&2
  exit 1
fi

IMAGE_URL="cr.yandex/${REGISTRY_ID}/${IMAGE_NAME}"

echo "==> Сборка Docker-образа..."
docker build -t "${IMAGE_URL}" .

echo "==> Авторизация в Yandex Container Registry..."
yc container registry configure-docker

echo "==> Push образа в реестр..."
docker push "${IMAGE_URL}"

echo "==> Деплой revision в Serverless Container..."
yc serverless container revision deploy \
  --container-id "${CONTAINER_ID}" \
  --image "${IMAGE_URL}" \
  --service-account-id "${SERVICE_ACCOUNT_ID}" \
  --folder-id "${FOLDER_ID}" \
  --env YC_S3_ENDPOINT="${YC_S3_ENDPOINT:-https://storage.yandexcloud.net}" \
  --env BUCKET_NAME="${BUCKET_NAME}" \
  --env YC_ACCESS_KEY_ID="${YC_ACCESS_KEY_ID}" \
  --env YC_SECRET_ACCESS_KEY="${YC_SECRET_ACCESS_KEY}"

echo "==> Готово. URL контейнера:"
yc serverless container get "${CONTAINER_ID}" --format json \
  | grep -o '"url": "[^"]*"' || true
