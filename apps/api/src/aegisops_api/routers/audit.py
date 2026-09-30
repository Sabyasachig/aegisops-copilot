from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_operator
from ..db.engine import get_db
from ..db.repository import list_audit_logs

router = APIRouter(tags=["audit"], dependencies=[Depends(get_current_user)])


@router.get("/audit")
async def audit_logs(
    incident_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(require_operator),
) -> dict:
    """Return a paginated audit trail for the incident or a filtered subset."""
    entries = await list_audit_logs(db, incident_id=incident_id, limit=limit, offset=offset)
    return {
        "audit_logs": [entry.model_dump(mode="json") for entry in entries],
        "count": len(entries),
        "limit": limit,
        "offset": offset,
        "actor": current_user,
    }
