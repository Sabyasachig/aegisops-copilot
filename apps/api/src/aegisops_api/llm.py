from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from .models import LLMProvider
from .settings import get_settings


def build_chat_model(
    provider: LLMProvider | None = None, model_name: str | None = None
) -> BaseChatModel:
    settings = get_settings()
    selected_provider = provider or settings.llm_provider
    selected_model = model_name or settings.llm_model

    if selected_provider == "groq":
        return ChatGroq(model=selected_model, temperature=0.1)
    if selected_provider == "openai":
        return ChatOpenAI(model=selected_model, temperature=0.1)
    if selected_provider == "anthropic":
        return ChatAnthropic(model=selected_model, temperature=0.1)

    raise ValueError(f"Unsupported provider: {selected_provider}")


@lru_cache(maxsize=8)
def get_chat_model(
    provider: LLMProvider | None = None, model_name: str | None = None
) -> BaseChatModel:
    return build_chat_model(provider=provider, model_name=model_name)
