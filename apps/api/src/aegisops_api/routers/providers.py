from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import ProviderInfo
from ..settings import get_settings

router = APIRouter(tags=["providers"], dependencies=[Depends(get_current_user)])


@router.get("/providers", response_model=ProviderInfo)
def providers() -> ProviderInfo:
    settings = get_settings()
    return ProviderInfo(
        provider=settings.llm_provider,
        model_name=settings.llm_model,
        tracing_enabled=settings.langsmith_tracing,
    )
