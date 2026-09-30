from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from aegisops_api.db.orm_models import AuditLogRow
from aegisops_api.db.repository import list_audit_logs, log_audit_event


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def test_log_audit_event_persists_and_filters_by_incident() -> None:
    async def _run() -> None:
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        base = datetime.now(UTC)
        rows = [
            AuditLogRow(
                id="AUD-001",
                actor="admin",
                action="incident_created",
                resource_id="INC-AUDIT-001",
                payload={"incident_id": "INC-AUDIT-001", "severity": "high"},
                created_at=base - timedelta(minutes=5),
            ),
            AuditLogRow(
                id="AUD-002",
                actor="operator",
                action="run_approved",
                resource_id="RUN-42",
                payload={"incident_id": "INC-AUDIT-001", "run_id": "RUN-42"},
                created_at=base,
            ),
        ]
        db.execute = AsyncMock(return_value=_Result(rows))

        entry = await log_audit_event(
            db,
            actor="system",
            action="audit_created",
            resource_id="INC-AUDIT-001",
            payload={"note": "test"},
        )
        entries = await list_audit_logs(db, incident_id="INC-AUDIT-001", limit=10)

        assert entry.action == "audit_created"
        assert [e.action for e in entries[:2]] == ["run_approved", "incident_created"]
        assert entries[0].actor == "operator"
        assert entries[0].payload["run_id"] == "RUN-42"

    asyncio.run(_run())


def test_list_audit_logs_supports_pagination() -> None:
    async def _run() -> None:
        db = MagicMock()
        base = datetime.now(UTC)
        db.execute = AsyncMock(
            return_value=_Result(
                [
                    AuditLogRow(
                        id=f"AUD-{i:03d}",
                        actor="system",
                        action=f"status_change_{i}",
                        resource_id="INC-AUDIT-002",
                        payload={"incident_id": "INC-AUDIT-002", "index": i},
                        created_at=base - timedelta(minutes=i),
                    )
                    for i in range(3)
                ]
            )
        )

        entries = await list_audit_logs(db, incident_id="INC-AUDIT-002", limit=2, offset=1)
        assert len(entries) == 2
        assert entries[0].action == "status_change_1"
        assert entries[1].action == "status_change_2"

    asyncio.run(_run())
