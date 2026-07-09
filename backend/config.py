"""Конфигурация приложения. Всё читается из .env, ничего не хардкодим."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    llm_base_url: str = Field(default="http://10.99.99.201:8000/v3")
    llm_model: str = Field(default="OpenVINO/Qwen3-14B-int8-ov")
    llm_api_key: str = Field(default="not-needed")
    llm_timeout: int = Field(default=300)

    # Поиск
    search_provider: str = Field(default="mock")  # mock | serper | dataforseo | gemini
    serper_api_key: str = Field(default="")
    dataforseo_login: str = Field(default="")
    dataforseo_password: str = Field(default="")

    # Gemini (Google AI Studio). Используется как:
    #  1) провайдер поиска цен с grounding (SEARCH_PROVIDER=gemini) — дёшево, одним
    #     вызовом даёт цену+ссылку без crawl4ai;
    #  2) резервная LLM, когда локальный OVMS недоступен (см. llm.py).
    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-3.1-flash-lite")
    gemini_base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    search_gl: str = Field(default="kz")
    search_hl: str = Field(default="ru")
    # NoDecode: не давать pydantic-settings json-парсить значение из .env —
    # строку «a,b,c» разбирает наш валидатор ниже.
    marketplaces: Annotated[List[str], NoDecode] = Field(
        default=["satu.kz", "technodom.kz", "sulpak.kz", "mechta.kz", "alser.kz", "kaspi.kz"]
    )
    max_prices_per_item: int = Field(default=5)

    # Матчинг
    match_confidence_min: float = Field(default=0.6)

    # ── Деплой на портал ai.knus.edu.kz (под слаг /agents/procurement) ──
    # Префикс под-пути на портале. Нужен FastAPI для корректных URL за reverse-proxy.
    # Локально — пусто. Читается из ROOT_PATH (совместимо с другими агентами вуза).
    root_path: str = Field(default="", validation_alias=AliasChoices("ROOT_PATH", "APP_ROOT_PATH"))
    # Разрешённые CORS-источники (через запятую). За nginx обычно не нужны.
    cors_origins: Annotated[List[str], NoDecode] = Field(default=[])
    # Каталог собранного React (dist). Если есть — FastAPI отдаёт и UI, и API.
    frontend_dist: str = Field(default="")
    # Заголовки forward_auth платформы для имени пользователя/админ-флага.
    auth_user_headers: str = Field(
        default="x-user-name,remote-name,x-forwarded-user,remote-user,x-auth-user"
    )
    auth_admin_header: str = Field(default="x-is-admin")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("marketplaces", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        """Списочные поля в .env — строка через запятую."""
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
