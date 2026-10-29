# Полная инструкция: GitHub + opencode + Streamlit + Yandex Serverless Container + Object Storage

Этот документ — единый источник правды, как подключить проект `video-app`
(персональный видеокаталог элитных таунхаусов в Подмосковье под брендом
**KASKAD**) к GitHub, развернуть backend в **Yandex Serverless Container**,
frontend в **Streamlit Community Cloud** и подключить **Yandex Object Storage**.

> **Ваше окружение (проверено):**
> - ОС Windows, терминал **PowerShell**
> - Git 2.51.2 установлен; есть Git Bash / Git CMD / Git GUI / **GitHub Desktop** / GitHub Copilot CLI
> - **Yandex Cloud CLI `yc` (1.31.0)** установлен
> - **`gh` (GitHub CLI 2.99.0)** установлен, но **ещё не авторизован**
> - Docker 29.1 установлен и работает

**Текущее состояние проекта (проверено):**
- `git init` сделан, ветка `main`, локальные коммиты есть:
  - `cf3b6c7` Initial commit
  - `c9b3803` Brand KASKAD (светлая тема, фото, фикс багов)
- Весь код перепроверен: компилируется, backend-образ собирается и стартует
  (`/health` → 200), frontend рендерится без ошибок, YAML-воркфлоу валидны.
- Модели `.joblib` НЕ в репозитории (папка `backend/model/` — только `.gitkeep`).

---

## Архитектура (как всё связано)

```
[Покупатель] ──▶ Streamlit (frontend, Streamlit Cloud)
                     │  POST /generate/ {полный вектор признаков}
                     ▼
               FastAPI (backend, Yandex Serverless Container)
                     │  1) классификация посёлка (model.joblib)
                     │  2) SHAP-факторы (explainer.joblib)
                     │  3) скачивание фрагментов из S3, склейка (ffmpeg/moviepy)
                     ▼
               Yandex Object Storage (видео) ──▶ публичная ссылка на ролик
```

- **GitHub** — хранит код и автоматически деплоит backend через GitHub Actions.
- **Streamlit Cloud** — хостит frontend (без серверов).
- **Yandex** — serverless-логика backend + хранилище видео/метрик.

---

## ЧАСТЬ 0. Авторизовать GitHub CLI (`gh`) — нужно СЕЙЧАС

`gh` установлен, но не авторизован. Это **единственный шаг, который я не могу
сделать за вас** (нужен вход в браузер). В PowerShell:

```powershell
# 0.1 Войти в GitHub
"C:\Program Files\GitHub CLI\gh.exe" auth login --hostname github.com --git-protocol https --web
```

- Откроется браузер: подтвердите вход в ваш аккаунт GitHub.
- Когда увидите «Success» — вернитесь в терминал.
- Проверка:
```powershell
"C:\Program Files\GitHub CLI\gh.exe" auth status
```

> Если хотите пользоваться просто `gh` без полного пути — перезапустите
> PowerShell/opencode (PATH обновится).

---

## ЧАСТЬ 1. Создать репозиторий и запушнуть код

### Способ А — автоматически через opencode (рекомендую)
После авторизации `gh` скажите мне: **«загрузи в github»** — я сам выполню:
```powershell
git add -A
git commit -m "deploy: connect repo"
gh repo create video-app --private --source=. --remote=origin --push
```
Флаг `--private` — код видите только вы. Можно `--public`.

### Способ Б — GitHub Desktop (без команд)
1. Откройте **GitHub Desktop** → войдите.
2. **File → Add Local Repository** → папка `video-app`.
3. **Publish repository** → **Private** → **Publish**. Код уйдёт на GitHub.

> `.gitignore` исключает: модели `.joblib`, CSV-метрики, секреты `.env`,
> `secrets.toml`, видео `*.mp4`, отчёты. Фото в `frontend/assets/` — в git.

---

## ЧАСТЬ 2. Yandex Cloud: подготовка ресурсов (один раз)

В PowerShell с установленным `yc`.

### 2.1. Авторизация и папка
```powershell
yc init          # браузер: выберите облако/фолдер
yc resource-manager folder list   # запомните FOLDER_ID (id папки)
```

### 2.2. Сервисный аккаунт + права
```powershell
# 1) Сервисный аккаунт для деплоя
yc iam service-account create --name video-deploy --folder-id <FOLDER_ID>
# 2) Права на контейнеры
yc resource-manager folder add-access-binding `
  --role container.admin --service-account-name video-deploy --folder-id <FOLDER_ID>
yc container registry add-access-binding `
  --role container-registry.images.puller `
  --service-account-name video-deploy --folder-id <FOLDER_ID>
# 3) Права на бакет (видео/метрики)
yc resource-manager folder add-access-binding `
  --role storage.editor --service-account-name video-deploy --folder-id <FOLDER_ID>
# запомните ID сервисного аккаунта:
yc iam service-account get --name video-deploy --folder-id <FOLDER_ID> --format json
```

### 2.3. Container Registry (реестр образов)
```powershell
yc container registry create --name video-registry --folder-id <FOLDER_ID>
# -> запомните REGISTRY_ID (id)
```

### 2.4. Serverless Container (контейнер-функция)
```powershell
yc serverless container create --name video-app --folder-id <FOLDER_ID>
# -> запомните CONTAINER_ID (id)
```

### 2.5. Статический ключ для S3 + OAuth-токен
```powershell
# Статический ключ (для доступа к Object Storage) — выдаётся на сервисный аккаунт
yc iam access-key create --service-account-id <SERVICE_ACCOUNT_ID>
# -> выдаст access_key_id (YC_ACCESS_KEY_ID) и secret (YC_SECRET_ACCESS_KEY)
```

**OAuth-токен** (для GitHub Actions):
1. Откройте https://oauth.yandex.ru/authorize?response_type=token&client_id=1a6990aa636648e9b2ef855fa7bec2fb
2. Разрешите доступ → получите токен (начинается с `y0_` или `AQ...`).
3. Скопируйте его (это **YC_OAUTH_TOKEN**).

---

## ЧАСТЬ 3. Yandex Object Storage: бакет и видео

### 3.1. Создать бакет
В консоли Yandex Cloud → **Object Storage** → **Создать бакет**:
- Имя: например `video-app-bucket` (или любое).
- Доступ: **публичный** (чтобы ссылки на ролики открывались без авторизации)
  или приватный + публичная ссылка через генерацию — для простоты выберите
  «публичное чтение».
- Доп. настройки по умолчанию.

### 3.2. Загрузить видео по структуре
Backend (в `backend/main.py`, словарь `VIDEO_PATH_MAP`) ищет ролики по пути:
```
video/<посёлок>/<категория>/<подкатегория>/...mp4
```
Код **устойчив к именам файлов** (`video1.mp4` / `video.mp4`) и к опечаткам
в названиях папок (`proirities`, `priotrities` и т.п.) — ищет первый `.mp4`
в нужной подкатегории.

- Загрузите видео в папку `video/` бакета (создайте структуру как в
  `VIDEO_PATH_MAP` в `main.py`).
- Метрики бэкенд пишет сам в папку `metrics/` (префикс `METRICS_S3_PREFIX`).

---

## ЧАСТЬ 4. Секреты GitHub для авто-деплоя backend

GitHub → ваш репозиторий → **Settings → Secrets and variables → Actions →
New repository secret**. Добавьте **8 секретов** (имена — точно как ниже):

| Имя секрета | Значение |
|-------------|----------|
| `YC_OAUTH_TOKEN` | OAuth-токен из ЧАСТИ 2.5 |
| `YC_FOLDER_ID` | id папки (ЧАСТЬ 2.1) |
| `YC_REGISTRY_ID` | id реестра (ЧАСТЬ 2.3) |
| `YC_CONTAINER_ID` | id контейнера (ЧАСТЬ 2.4) |
| `YC_SERVICE_ACCOUNT_ID` | id сервисного аккаунта video-deploy (ЧАСТЬ 2.2) |
| `YC_BUCKET_NAME` | имя бакета (ЧАСТЬ 3.1) |
| `YC_ACCESS_KEY_ID` | статический ключ (access key id, ЧАСТЬ 2.5) |
| `YC_SECRET_ACCESS_KEY` | секрет статического ключа (ЧАСТЬ 2.5) |

> В workflow `.github/workflows/backend-deploy.yml` уже прописан полный деплой:
> checkout → docker build backend → push в YC registry → deploy revision.
> Он сработает автоматически при push в `backend/` в ветку `main`.

---

## ЧАСТЬ 5. Модели и данные для backend

Backend работает с моделями из `backend/model/` — **их надо положить до сборки**:

```
backend/model/global_best_model.joblib   # классификация посёлка
backend/model/xgb_explainer.joblib       # SHAP-объяснитель
backend/data/feature_names.txt           # список признаков (по строкам)
```
- Сейчас в `backend/model/` только `.gitkeep`.
- Для авто-деплоя через Actions модели нужно добавить в git **или** скачивать
  на шаге сборки (git-lfs или S3).
- **Важно:** `frontend/data/feature_names.txt` и `backend/data/feature_names.txt`
  должны совпадать — иначе вектор признаков не сойдётся (это ещё не сделано,
  см. ЧАСТЬ 8).

> Пока моделей нет, контейнер стартует, но `/health` вернёт
> `"status":"degraded"` — это НОРМАЛЬНО и ожидаемо.

---

## ЧАСТЬ 6. Деплой frontend в Streamlit Community Cloud

1. Зайдите на https://streamlit.io/cloud → **Sign in with GitHub**.
2. **New app** → выберите репозиторий `video-app`.
3. **Branch**: `main`. **Main file path**: `frontend/app.py`. **Deploy**.
4. В приложении → **Settings → Secrets** добавьте:
```toml
BACKEND_URL = "https://<url-вашего-serverless-container>"
```
   `<url-...>` — адрес контейнера из ЧАСТИ 7.
5. **Save → Rerun** (перезапуск приложения).

Фото лежат в `frontend/assets/` и загружаются из репозитория — дополнительной
настройки не требуется.

---

## ЧАСТЬ 7. Проверить деплой backend

После пуша в `main` (папка `backend/`) GitHub Actions соберёт и задеплоит
контейнер. Проверить URL:
```powershell
yc serverless container get <CONTAINER_ID> --format json
```
В выводе найдите поле `"url"` (например `https://bfl...apigw.yandexcloud.net`).
Это и есть `BACKEND_URL`.

Проверка живости:
- Откройте `https://<URL>/docs` (Swagger) или `https://<URL>/health`.

---

## ЧАСТЬ 8. Что нужно сделать СЕЙЧАС (ваш чек-лист)

1. **Авторизовать `gh`** (ЧАСТЬ 0) — скажите мне «готово».
2. **«Загрузи в github»** — я создам репозиторий и запушу код.
3. **Yandex Cloud**: выполнить ЧАСТЬ 2 (yc), ЧАСТЬ 3 (бакет + видео).
4. **Добавить 8 секретов** в GitHub (ЧАСТЬ 4).
5. **Положить модели** `.joblib` и `backend/data/feature_names.txt` (ЧАСТЬ 5),
   обновить `frontend/data/feature_names.txt` под реальные колонки модели.
6. **Streamlit Cloud**: подключить frontend (ЧАСТЬ 6), задать `BACKEND_URL`.
7. **Проверить** адрес контейнера и `/health` (ЧАСТЬ 7).

Напоминания (из прошлых проверок):
- `frontend/data/feature_names.txt` — пока ЗАГЛУШКА; заменить реальными фичами.
- `.joblib` — иначе backend фактически не предсказывает (только `degraded`).
- `st.components.v1.html` в `frontend/analytics.py` — deprecated, удалят после
  2026-06-01; сейчас работает, но имейте в виду на будущее.

---

## Частые вопросы

**Что умеет opencode с GitHub?**
Всё, что умеет ваш локальный `gh`/git: создание репо, коммиты, push, PR,
запуск Actions. Работает под вашим аккаунтом — отдельного «подключения»
opencode к GitHub нет.

**Можно ли без GitHub?**
Да: backend деплоится вручную через `bash deploy.sh` (в `backend/`),
frontend — локально `streamlit run frontend/app.py`. GitHub нужен только для
авто-деплоя и Streamlit Cloud.

**Почему сайт kaskad-n.ru не в проекте?**
Мы взяли с сайта только: фирменный стиль (светлый, зелёный `#168e38`,
Manrope), контакты (+7 495 222-58-58), фото 4 разрешённых проектов
(Каскад Парк, Академия Парк, Федоскино Парк, Парк Апрель) и общие фоны
без названий проектов. Логотипы/названия других проектов НЕ использовались.
⚠️ У сайта истёк SSL-сертификат на прокси картинок — стоит сообщить
владельцам.
