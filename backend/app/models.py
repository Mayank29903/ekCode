import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, Numeric, String,
                        Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return uuid.uuid4()


class Cpse(Base):
    __tablename__ = "cpse"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(80))


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    cpse_id: Mapped[int | None] = mapped_column(ForeignKey("cpse.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (CheckConstraint("role in ('admin','data_steward','cpse_user','auditor')"),)


class IngestJob(Base):
    __tablename__ = "ingest_job"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    cpse_id: Mapped[int] = mapped_column(ForeignKey("cpse.id"))
    filename: Mapped[str] = mapped_column(String(300))
    path: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="upload")
    status: Mapped[str] = mapped_column(String(20), default="uploaded")   # uploaded|queued|running|done|error
    stage: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    processed_rows: Mapped[int] = mapped_column(Integer, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, default=0)
    column_map: Mapped[dict | None] = mapped_column(JSONB)
    report: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Every stage change touches it; a queued/running job that stops changing is shown as stalled.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class RawMaterial(Base):
    __tablename__ = "raw_material"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cpse_id: Mapped[int] = mapped_column(ForeignKey("cpse.id"))
    legacy_code: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    long_text: Mapped[str | None] = mapped_column(Text)
    uom_raw: Mapped[str | None] = mapped_column(String(20))
    uom_code: Mapped[str | None] = mapped_column(String(8))
    material_group: Mapped[str | None] = mapped_column(String(40))
    unit_price: Mapped[float | None] = mapped_column(Numeric(14, 2))
    annual_qty: Mapped[float | None] = mapped_column(Numeric(14, 2))
    source: Mapped[str] = mapped_column(String(20), default="upload")
    row_hash: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingest_job.id"))
    status: Mapped[str] = mapped_column(String(20), default="ingested")  # ingested|embedded|matched|mapped
    norm_text: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSONB)
    attr_confidence: Mapped[dict | None] = mapped_column(JSONB)
    embedding = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("cpse_id", "legacy_code"),)


class NationalMaterial(Base):
    __tablename__ = "national_material"
    nmc: Mapped[str] = mapped_column(String(24), primary_key=True)
    noun: Mapped[str | None] = mapped_column(String(60))
    standard_description: Mapped[str] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    unspsc: Mapped[str | None] = mapped_column(String(8))
    uom_code: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20), default="active")
    successor_nmc: Mapped[str | None] = mapped_column(ForeignKey("national_material.nmc"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class CodeMapping(Base):
    __tablename__ = "code_mapping"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_material_id: Mapped[int] = mapped_column(ForeignKey("raw_material.id"), unique=True)
    nmc: Mapped[str] = mapped_column(ForeignKey("national_material.nmc"))
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="approved")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MatchPair(Base):
    __tablename__ = "match_pair"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    a_id: Mapped[int] = mapped_column(ForeignKey("raw_material.id"))
    b_id: Mapped[int] = mapped_column(ForeignKey("raw_material.id"))
    score: Mapped[float] = mapped_column(Float)
    match_type: Mapped[str] = mapped_column(String(30))
    features: Mapped[dict] = mapped_column(JSONB)
    explanation: Mapped[list] = mapped_column(JSONB)
    gate_failures: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[str] = mapped_column(String(20), default="suggested")
    model_version: Mapped[str | None] = mapped_column(String(40))
    impact: Mapped[float] = mapped_column(Float, default=0)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("a_id", "b_id"), CheckConstraint("a_id < b_id"))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_email: Mapped[str | None] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(80), index=True)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    path: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Setting(Base):
    __tablename__ = "setting"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)


class ApiKey(Base):
    __tablename__ = "api_key"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80))
    prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Webhook(Base):
    __tablename__ = "webhook"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str] = mapped_column(String(80))
    events: Mapped[list[str]] = mapped_column(ARRAY(String))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_status: Mapped[int | None] = mapped_column(Integer)
