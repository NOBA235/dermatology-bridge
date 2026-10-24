"""SQLAlchemy 2.x ORM models matching the canonical Dermatology Bridge DDL."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
     JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


BigSerialPK = BigInteger().with_variant(Integer(), "sqlite")
JsonbPayload = JSON().with_variant(JSONB(), "postgresql")


class Clinic(Base):
    """Clinics table."""

    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    clinicians: Mapped[list[Clinician]] = relationship(back_populates="clinic")
    patients: Mapped[list[Patient]] = relationship(back_populates="clinic")


class Clinician(Base):
    """Clinicians table."""

    __tablename__ = "clinicians"
    __table_args__ = (
        Index("idx_clinicians_clinic", "clinic_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    clinic: Mapped[Clinic] = relationship(back_populates="clinicians")


class Patient(Base):
    """Patients table."""

    __tablename__ = "patients"
    __table_args__ = (
        Index("idx_patients_clinic", "clinic_id"),
        Index("idx_patients_external_ref", "clinic_id", "external_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clinics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    clinic: Mapped[Clinic] = relationship(back_populates="patients")
    visits: Mapped[list[Visit]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    treatment_flags: Mapped[list[TreatmentFlag]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class Visit(Base):
    """Visits table."""

    __tablename__ = "visits"
    __table_args__ = (
        CheckConstraint(
            "youcam_status IN ('pending','success','failed')",
            name="ck_visits_youcam_status",
        ),
        Index("idx_visits_patient_date", "patient_id", text("visit_date DESC")),
        Index(
            "idx_visits_pending",
            "youcam_status",
            postgresql_where=text("youcam_status <> 'success'"),
            sqlite_where=text("youcam_status <> 'success'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    visit_date: Mapped[date] = mapped_column(Date, nullable=False)
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    routine_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False)
    image_storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    youcam_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    youcam_task_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    youcam_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    raw_result: Mapped[dict[str, Any] | None] = mapped_column(
        JsonbPayload, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
    )

    patient: Mapped[Patient] = relationship(back_populates="visits")
    concern_scores: Mapped[list[ConcernScore]] = relationship(
        back_populates="visit", cascade="all, delete-orphan"
    )


class ConcernScore(Base):
    """Concern scores table."""

    __tablename__ = "concern_scores"
    __table_args__ = (
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_concern_scores_score",
        ),
        CheckConstraint(
            "severity IN ('clear','mild','moderate','severe')",
            name="ck_concern_scores_severity",
        ),
        UniqueConstraint("visit_id", "concern", name="uq_concern_scores_visit_concern"),
        Index("idx_concern_scores_concern", "concern"),
        Index("idx_concern_scores_visit", "visit_id"),
    )

    id: Mapped[int] = mapped_column(
        BigSerialPK, primary_key=True, autoincrement=True
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visits.id", ondelete="CASCADE"),
        nullable=False,
    )
    concern: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    mask_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    mask_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    visit: Mapped[Visit] = relationship(back_populates="concern_scores")


class TreatmentFlag(Base):
    """Treatment flags table (materialized; regenerated per patient via delete-then-insert)."""

    __tablename__ = "treatment_flags"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('improving','stalled','worsening','insufficient_data')",
            name="ck_treatment_flags_verdict",
        ),
        Index("idx_treatment_flags_patient", "patient_id"),
        Index(
            "uq_treatment_flags_current",
            "patient_id",
            "concern",
            "latest_visit_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(
        BigSerialPK, primary_key=True, autoincrement=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    concern: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_visit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visits.id", ondelete="CASCADE"),
        nullable=False,
    )
    latest_visit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("visits.id", ondelete="CASCADE"),
        nullable=False,
    )
    delta: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    pct_change: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=func.now(),
    )

    patient: Mapped[Patient] = relationship(back_populates="treatment_flags")
    baseline_visit: Mapped[Visit] = relationship(foreign_keys=[baseline_visit_id])
    latest_visit: Mapped[Visit] = relationship(foreign_keys=[latest_visit_id])
