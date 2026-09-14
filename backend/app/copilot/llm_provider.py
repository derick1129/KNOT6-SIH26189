"""
LLM provider abstraction. Every other copilot module talks to `LLMProvider`,
never to a specific vendor SDK -- swapping providers (or adding a second
one) is a one-file change here, not a rewrite of `copilot.py`.

Uses `httpx` (already a backend dependency for other purposes) to call the
Anthropic Messages API directly over HTTP rather than pulling in the full
`anthropic` SDK as a new dependency -- the wire protocol needed here (one
system prompt, one user message, one text response) is small enough that a
raw HTTP call is simpler than a new dependency, per the brief's "no
unnecessary dependencies".

If `ANTHROPIC_API_KEY` is not set, `get_llm_provider()` returns a
`NullLLMProvider` whose `available` is `False` -- `InvestigationCopilot`
checks this before doing any retrieval work and returns a clear
"AI Copilot requires an AI provider configuration" state instead of ever
faking a response (see docs in copilot.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

import httpx

from app.core.config import get_settings


class LLMProvider(ABC):
    available: bool

    @abstractmethod
    def generate(self, system: str, user_message: str) -> str:
        """Return the model's plain-text reply. Raises LLMError on failure."""
        ...


class LLMError(RuntimeError):
    pass


class NullLLMProvider(LLMProvider):
    """No provider configured. `generate()` is never called in this state --
    callers must check `available` first (see InvestigationCopilot.answer)."""
    available = False

    def generate(self, system: str, user_message: str) -> str:
        raise LLMError("No LLM provider is configured.")


class AnthropicProvider(LLMProvider):
    available = True

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    def generate(self, system: str, user_message: str) -> str:
        try:
            resp = httpx.post(
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 1024,
                    "system": system,
                    "messages": [{"role": "user", "content": user_message}],
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            parts = data.get("content", [])
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            if not text:
                raise LLMError("LLM provider returned an empty response.")
            return text
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"LLM provider request failed: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM provider request failed: {exc}") from exc


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    # Generic LLM_PROVIDER/LLM_API_KEY/LLM_MODEL env vars take priority when
    # set; ANTHROPIC_API_KEY/ANTHROPIC_MODEL remain fully supported so
    # existing configuration keeps working unchanged either way.
    provider_name = (settings.llm_provider or "anthropic").strip().lower()
    api_key = settings.llm_api_key or settings.anthropic_api_key
    model = settings.llm_model or settings.anthropic_model
    # "anthropic" is the only provider actually implemented today (see this
    # module's docstring for why: a small, tested, dependency-free HTTP
    # call). An unset/unrecognized provider name degrades to NullLLMProvider
    # -- the same honest "not configured" state as no API key at all --
    # rather than guessing at an untested vendor integration.
    if not api_key or provider_name != "anthropic":
        return NullLLMProvider()
    return AnthropicProvider(api_key, model, settings.anthropic_base_url)
