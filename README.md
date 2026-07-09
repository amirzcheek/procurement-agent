# Анализатор закупок (procurement price-check)

Локальное приложение для университета (Казахстан): загрузить коммерческое предложение
(КП) в `.xlsx` или текстовом `.pdf`, извлечь позиции, найти рыночные цены на казахстанских
площадках через веб-поиск, сопоставить товары, сравнить с ценой из КП и выдать отчёт с
флагами завышения.

> ⚠️ **Дисклеймер.** Результат — предварительный анализ. Цены найдены автоматически и
> требуют проверки человеком. Это обоснованное **подозрение** для ручной проверки, а не
> окончательное заключение.

## Архитектура (этапы пайплайна)

Каждый этап — отдельный модуль, тестируемый изолированно (`backend/`):

| Модуль | Этап |
|---|---|
| `extract.py` | Извлечение сырого текста таблицы (xlsx / текстовый PDF; скан → ошибка «нужен OCR»). |
| `parse_items.py` | Структурирование в `Item` через LLM + Pydantic-валидация (retry ×2). |
| `normalize.py` | Короткий поисковый запрос + множитель приведения к единице КП. |
| `search.py` | Поиск ссылок: `MockProvider` / `SerperProvider` / `DataForSEOProvider` (заглушка). |
| `fetch_price.py` | Цена со страницы: crawl4ai (рендер JS → markdown) → LLM → `PriceHit`. |
| `match.py` | Product matching через LLM (`Matcher`-интерфейс; задел под `QdrantMatcher`). |
| `compare.py` | Приведение к единице, медиана/мин/макс, дельта %, флаги. |
| `report.py` | Экспорт в xlsx (лист позиций + сводка, заливка по флагам). |
| `pipeline.py` | Оркестрация по позициям (последовательно), изоляция ошибок, лог этапов. |
| `app.py` | FastAPI: `POST /analyze` (SSE-прогресс), `GET /export/{job_id}`. |
| `providers/goszakup_provider.py`, `providers/nct_provider.py` | Заглушки Фазы 2 (реальные закупочные цены, идентификация по NTIN/GTIN). |

**Флаги:** 🟢 green — КП ≤ медиана×1.1; 🟡 yellow — до ×1.3; 🔴 red — выше ×1.3;
⚪ gray — нет подтверждённых совпадений или низкий средний confidence (на ручную проверку).

## Требования

- Windows, Python 3.11+, Node.js 18+.
- Локальный LLM (OVMS/Qwen3, OpenAI-совместимый) — адрес в `.env`.
- crawl4ai требует браузер Playwright (см. шаг ниже). Для отладки можно работать в режиме
  `SEARCH_PROVIDER=mock` — он не ходит ни в сеть, ни в crawl4ai.

## Настройка

```bash
# 1) Скопировать конфиг
copy .env.example backend\.env
# отредактировать backend\.env (LLM_BASE_URL, SERPER_API_KEY и т.д.)
```

## Запуск — backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# для реального fetch_price (не mock) — установить браузер для crawl4ai:
python -m playwright install chromium
uvicorn app:app --port 8090
```

## Запуск — frontend

```bash
cd frontend
npm install
npm run dev
# открыть http://localhost:5173
```

Vite проксирует `/api` → `http://localhost:8090`, так что бэкенд и фронтенд работают вместе
без правки URL.

## Порядок проверки

1. **Сначала `SEARCH_PROVIDER=mock`** — прогнать пайплайн целиком без поисковых API
   (LLM всё ещё нужен для разбора позиций). Поиск, цены и матчинг подменяются заглушками,
   флаги и отчёт считаются по-настоящему.
2. Затем вписать `SERPER_API_KEY` и переключить `SEARCH_PROVIDER=serper`, прогнать на
   реальном КП. Поиск — обычная органика `google.kz` (НЕ Google Shopping: для KZ Shopping
   не работает), фильтр по площадкам через `site:`.

## Тесты

Изолированные модульные тесты (без LLM/сети):

```bash
cd backend
.venv\Scripts\activate
pytest
```

## API

- `POST /analyze` — multipart-загрузка файла. Ответ — поток **SSE**: события
  `job`, `extract`, `parsed`, `item_start`, `item_done`, `done`, `error`.
- `GET /export/{job_id}` — xlsx-отчёт по завершённому анализу.
- `GET /config` — безопасная часть конфигурации для UI.
- `GET /health` — проверка живости.

## Принципы

- Результат — обоснованное **подозрение** для ручной проверки, не вердикт.
- Изоляция ошибок: сбой на одной позиции/источнике не роняет весь анализ.
- Логирование каждого этапа (извлечено / запрос / найдено / matching-решение).
- LLM-таймауты 180–300 с (`LLM_TIMEOUT`).

## Фаза 2 (задел, не реализовано)

- `goszakup_provider.py` — GraphQL `goszakup.gov.kz` (реальные закупочные цены, токен ЦЭФ).
- `nct_provider.py` — НКТ Open API (идентификация по NTIN/GTIN).
- `QdrantMatcher` — эмбеддинги (Ollama) + векторный поиск вместо/в дополнение к LLM-матчингу.

Провайдеры подключаются через единые интерфейсы (`ReferenceProvider`, `Matcher`,
`PriceSearchProvider`) — добавление не ломает пайплайн.

## Деплой (позже)

Структура готова к докеризации и деплою на `ai.knus.edu.kz` под слагом
`/agents/procurement` (`APP_ROOT_PATH` для backend, `base: './'` + прокси `/api` для фронта).
Сейчас — только локальный запуск.
