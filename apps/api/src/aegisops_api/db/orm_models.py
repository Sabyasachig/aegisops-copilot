from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .engine import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    open_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    runs: Mapped[list[AgentRunRow]] = relationship(
        "AgentRunRow", back_populates="incident", cascade="all, delete-orphan"
    )


class AgentRunRow(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_incident_id", "incident_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    artifact_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    incident: Mapped[IncidentRow] = relationship("IncidentRow", back_populates="runs")
