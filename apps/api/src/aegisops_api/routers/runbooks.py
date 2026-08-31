"""Admin endpoint for uploading runbooks into the RAG knowledge base."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import require_admin
from ..db.engine import get_db
from ..settings import get_settings

router = APIRouter(prefix="/admin", tags=["runbooks"])


class UploadRunbookRequest(BaseModel):
    title: str
    service: str | None = None
    content: str


@router.post("/runbooks", status_code=201)
async def upload_runbook(
    body: UploadRunbookRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(require_admin),
) -> dict:
    """Chunk, embed, and store a Markdown runbook in the vector knowledge base.

    Requires admin role.  Returns ``422`` when memory is not enabled.
    """
    settings = get_settings()
    if not settings.memory_enabled:
        raise HTTPException(
            status_code=422,
            detail=(
                "Runbook storage is disabled. "
                "Set AIOPS_MEMORY_ENABLED=true and run Alembic migration 0004/0005."
            ),
        )

    from ..memory import store_runbook  # noqa: PLC0415

    n_chunks = await store_runbook(
        db,
        title=body.title,
        service=body.service,
        content=body.content,
        source_path="api",
    )
    return {
        "title": body.title,
        "service": body.service,
        "chunks_stored": n_chunks,
        "uploaded_by": current_user,
    }
