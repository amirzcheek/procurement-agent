"""ORM-модели базы знаний закупок (Этап 1).

Схема заложена расширяемой под Этап 2 (проверки характеристик/условий, аналитика,
поставщики, dashboard). Векторные поля — pgvector (1024d, snowflake-arctic-embed2).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import get_settings
from db import Base

_DIM = get_settings().embedding_dim


class User(Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="procurer")  # procurer|manager|admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    bin_iin: Mapped[Optional[str]] = mapped_column(String(20), index=True)  # БИН/ИИН
    contacts: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    number: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    date: Mapped[Optional[date]] = mapped_column(Date)
    customer: Mapped[Optional[str]] = mapped_column(String(500))
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"))
    subject: Mapped[Optional[str]] = mapped_column(Text)
    funding_source: Mapped[Optional[str]] = mapped_column(String(500))
    total_sum: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))
    delivery_term: Mapped[Optional[str]] = mapped_column(String(500))
    warranty: Mapped[Optional[str]] = mapped_column(String(500))
    payment_terms: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|checked
    created_by: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    supplier: Mapped[Optional[Supplier]] = relationship()


class CommercialOffer(Base):
    __tablename__ = "commercial_offers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"))
    date: Mapped[Optional[date]] = mapped_column(Date)
    source_file: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LineItem(Base):
    __tablename__ = "line_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contracts.id"))
    offer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("commercial_offers.id"))
    name: Mapped[str] = mapped_column(Text)
    canonical_name: Mapped[Optional[str]] = mapped_column(Text, index=True)
    model: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    category: Mapped[Optional[str]] = mapped_column(String(300), index=True)
    specs: Mapped[Optional[dict]] = mapped_column(JSONB)
    qty: Mapped[Optional[float]] = mapped_column(Numeric(18, 3))
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))
    total_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 2))
    ntin: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(_DIM))
    purchase_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceHistory(Base):
    """Внутренняя история цен (из подтверждённых договоров/КП)."""

    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_key: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    item_name: Mapped[str] = mapped_column(Text)
    model: Mapped[Optional[str]] = mapped_column(String(300))
    manufacturer: Mapped[Optional[str]] = mapped_column(String(300))
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2))
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"))
    contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contracts.id"))
    purchase_date: Mapped[Optional[date]] = mapped_column(Date, index=True)


class PriceSearchHistory(Base):
    """История веб-поиска цен (каждый результат Gemini grounded search)."""

    __tablename__ = "price_search_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    query: Mapped[Optional[str]] = mapped_column(Text)
    item_name: Mapped[Optional[str]] = mapped_column(Text)
    canonical_key: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    model: Mapped[Optional[str]] = mapped_column(String(300))
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(10), default="KZT")
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_site: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    found_at: Mapped[date] = mapped_column(Date, index=True)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(_DIM))


class Check(Base):
    __tablename__ = "checks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contracts.id"))
    type: Mapped[str] = mapped_column(String(20))  # specs|price|qty|conditions
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    risk_level: Mapped[Optional[str]] = mapped_column(String(10))  # low|medium|high
    findings: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("contracts.id"))
    kind: Mapped[Optional[str]] = mapped_column(String(50))
    filename: Mapped[Optional[str]] = mapped_column(String(500))
    path: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(255))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[str]] = mapped_column(String(50))
    details: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
