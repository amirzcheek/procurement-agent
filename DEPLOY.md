# Развёртывание агента «Анализатор закупок» на портале ai.knus.edu.kz

Агент подключается под-путём основного домена — `https://ai.knus.edu.kz/agents/procurement/`
(как `content-generator`, `course-dev` и т.д.), **единым сервисом**: FastAPI отдаёт и
React-интерфейс, и API.

## Раскладка инфраструктуры

> Адреса серверов (`<NGINX_HOST>`, `<WEB_HOST>`, `<LLM_HOST>`) — плейсхолдеры.
> Реальные значения держим только в `.env` на сервере, в репозиторий не коммитим.

```
[ Браузер ] → HTTPS → [ nginx/Caddy основного домена (<NGINX_HOST>, TLS портала) ]
                          │  location /agents/procurement/   (префикс срезается)
                          ▼
                   [ web-сервер (<WEB_HOST>) ]
                   procurement: FastAPI/uvicorn (React + API в одном сервисе, :8080)
                          │  LLM_BASE_URL          ├─ Serper (веб-поиск google.kz)
                          ▼                        └─ crawl4ai (Chromium, рендер страниц)
                   [ LLM (OVMS/Qwen3, <LLM_HOST>:8000/v3) ]
```

- Сервис **не торчит в интернет** — слушает внутренний адрес, порт 8080 закрыт
  фаерволом для всех, кроме nginx/Caddy-хоста.
- TLS и домен — уже на реверс-прокси портала; **отдельный сертификат не нужен**,
  добавляется только `location`/`handle_path`-блок.
- Прогресс анализа идёт по **SSE** — на прокси обязательно отключить буферизацию
  (nginx `proxy_buffering off`, Caddy `flush_interval -1`).

> **Slug агента** — `procurement`. Он встречается в трёх местах и должен совпадать:
> `ROOT_PATH` и `VITE_BASE`/`VITE_API_BASE` (сборка) и `location`/`handle_path` в прокси.

---

## 1. Код и переменные окружения (web-сервер `<WEB_HOST>`)

```bash
git clone <repo-url> procurement
cd procurement
cp .env.example .env
nano .env
```

Ключевое в `.env`:
```ini
LLM_BASE_URL=http://<LLM_HOST>:8000/v3        # OVMS/Qwen3 (путь /v3!)
LLM_MODEL=OpenVINO/Qwen3-14B-int8-ov
LLM_TIMEOUT=300

SEARCH_PROVIDER=serper                          # mock для проверки без API
SERPER_API_KEY=<ключ serper.dev>
MARKETPLACES=satu.kz,technodom.kz,sulpak.kz,mechta.kz,alser.kz,kaspi.kz

ROOT_PATH=/agents/procurement                   # под-путь портала
VITE_BASE=/agents/procurement/
VITE_API_BASE=/agents/procurement
BIND_HOST=127.0.0.1                             # для systemd-варианта
```

> Docker + LLM на том же хосте — используйте `host.docker.internal` в `LLM_BASE_URL`
> и раскомментируйте `extra_hosts` в `docker-compose.yml`.

---

## 2. Запустить сервис — Docker ИЛИ systemd

### Вариант A — Docker (рекомендуется)

Сборка соберёт React (под под-путь) и упакует с FastAPI. По умолчанию образ
**лёгкий** — без crawl4ai/Chromium (для `SEARCH_PROVIDER=gemini`/`mock` они не нужны):

```bash
docker compose up -d --build
docker exec procurement curl -s http://localhost:8080/health   # {"status":"ok"}
```

> Нужен `SEARCH_PROVIDER=serper` (рендер страниц браузером)? Соберите с браузером:
> `INSTALL_CRAWL=true docker compose up -d --build` — образ станет заметно тяжелее.

### Вариант B — systemd (без Docker)

Шаги (сборка фронта, venv, установка Chromium, юнит) — в комментариях
[`procurement.service`](procurement.service).

---

## 3. Фаервол (порт 8080 только для прокси-хоста)

```bash
sudo ufw allow from <NGINX_HOST> to any port 8080 proto tcp
sudo ufw deny 8080
```
Проверка с прокси-сервера: `curl http://<WEB_HOST>:8080/health`.

---

## 4. Подключить под-путь к реверс-прокси

### Caddy (как на платформе — с гейтингом forward_auth)

Готовый фрагмент — [`caddy/Caddyfile.example`](caddy/Caddyfile.example). Сервис
доступен Caddy по имени `procurement:8080` в общей docker-сети платформы. `handle_path`
срезает слаг — бэкенд видит `/`, `/config`, `/analyze`, `/export`, `/auth/session`, `/assets`:

```caddy
handle_path /agents/procurement/* {
    forward_auth web:3000 {
        uri /api/auth/agent/Procurement
        # copy_headers Remote-Name Remote-User Remote-Groups X-Is-Admin
    }
    reverse_proxy procurement:8080 {
        flush_interval -1   # SSE-прогресс анализа
    }
}
redir /agents/procurement /agents/procurement/ 308
```

Имя пользователя и «Админка» в навбаре берутся из `GET /auth/session` (backend читает
заголовки, прокинутые `forward_auth` через `copy_headers`).

### nginx (альтернатива, без гейтинга)

В конфиге основного домена добавить содержимое
[`nginx/agent-location.conf`](nginx/agent-location.conf) (внутри `server { listen 443 ssl }`),
затем `sudo nginx -t && sudo systemctl reload nginx`. Слеш в `proxy_pass http://...:8080/;`
**обрезает** префикс; `proxy_buffering off` обязателен для SSE.

---

## 5. Карточка агента на портале

В реестре агентов портала добавить ссылку на `/agents/procurement/`.

---

## 6. Проверка снаружи

1. Открыть `https://ai.knus.edu.kz/agents/procurement/` — загрузится интерфейс
   (навбар KNUS Digital, дисклеймер, загрузка файла).
2. Сначала с `SEARCH_PROVIDER=mock` — прогнать пайплайн целиком (нужен только LLM).
3. Затем `SEARCH_PROVIDER=serper` + ключ — реальный КП с живыми ссылками.
4. API напрямую: `curl https://ai.knus.edu.kz/agents/procurement/config`.

---

## Замечания

- **Порядок проверки:** mock → serper. mock не тратит поисковый API и не требует
  браузера, но LLM (`<LLM_HOST>:8000/v3`) нужен всегда — на нём идёт разбор позиций.
- **Скорость.** В реальном режиме на позицию: поиск → рендер до `MAX_PRICES_PER_ITEM`
  страниц (Chromium) → LLM-извлечение цены + матчинг. На CPU это медленно —
  прокси-таймауты подняты до 600с.
- **Изоляция ошибок.** Сбой на одной позиции/источнике не роняет весь анализ;
  недоступные страницы помечаются, LLM-таймаут по позиции возвращает понятную ошибку.

## Фаза 2 (задел в коде, не активно)

- `backend/providers/goszakup_provider.py` — реальные закупочные цены (GraphQL, токен ЦЭФ).
- `backend/providers/nct_provider.py` — идентификация по NTIN/GTIN (НКТ Open API).
- `QdrantMatcher` — эмбеддинги + векторный поиск вместо/в дополнение к LLM-матчингу.
  Все три подключаются через существующие интерфейсы, не ломая пайплайн.
