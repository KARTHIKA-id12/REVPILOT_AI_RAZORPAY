"""AI provider abstraction. The Growth Agent and AI Buyer depend on this
interface only — swapping between the free Hugging Face provider and the
Mock provider never touches agent logic, tool contracts, or the action
pipeline."""

from typing import Protocol


class AIProvider(Protocol):
    def complete(self, *, system: str, messages: list[dict], response_schema: dict | None = None) -> str: ...


class MockAIProvider:
    """Deterministic canned-but-structured responses so the whole app runs
    with zero external AI cost. Real tool calls / DB grounding still run —
    only the natural-language synthesis step is mocked."""

    def complete(self, *, system: str, messages: list[dict], response_schema: dict | None = None) -> str:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return (
            f'{{"intent": "ANSWER", "reason": "demo-mode response", '
            f'"summary": "Mock AI provider received: {last_user[:80]}"}}'
        )


def get_ai_provider() -> AIProvider:
    from app.core.config import get_settings

    settings = get_settings()
    if settings.AI_PROVIDER == "huggingface" and settings.AI_API_KEY:
        from app.agents.huggingface_provider import HuggingFaceProvider

        return HuggingFaceProvider(api_key=settings.AI_API_KEY, model=settings.AI_MODEL)
    return MockAIProvider()
