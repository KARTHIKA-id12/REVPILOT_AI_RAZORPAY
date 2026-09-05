"""Free/open-model provider via Hugging Face's Inference Providers router.

Deliberately NOT OpenAI or Gemini: this project intentionally avoids paid
LLM APIs. Hugging Face's router (https://huggingface.co/docs/inference-providers)
fronts many open-weight models (Llama, Qwen, DeepSeek, Mistral, and more)
behind one OpenAI-compatible endpoint, with a genuine free tier for a
personal access token — no paid subscription required to run this.

Get a free token: https://huggingface.co/settings/tokens/new
  -> create a "fine-grained" token with the "Make calls to Inference
     Providers" permission enabled, then set it as AI_API_KEY.

This file is the ONLY place that talks to Hugging Face. Everything that
happens with its output afterwards (schema validation, policy checks,
financial recomputation, permission checks) is identical regardless of
which provider produced the text — see app/agents/service.py and
app/agents/intent_schema.py. The model is never trusted with money; it
only ever proposes a bounded, closed-set intent that deterministic code
validates and recomputes before anything happens.
"""
import json
import re

import httpx

from app.core.errors import AppError

ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"

# A small, broadly-available open-weight instruct model on the HF router's
# free tier. Overridable via the AI_MODEL setting -- check
# https://huggingface.co/docs/inference-providers for the current free-tier
# catalog, since which models are free-tier-eligible changes over time.
DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class HuggingFaceProvider:
    def __init__(self, api_key: str, model: str | None = None, timeout: float = 20.0):
        self._api_key = api_key
        self._model = model or DEFAULT_MODEL
        self._timeout = timeout

    def complete(self, *, system: str, messages: list[dict], response_schema: dict | None = None) -> str:
        payload: dict = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0,
        }
        if response_schema is not None:
            # Best-effort: most models routed through HF support this,
            # but not all backends honor it identically. The system
            # prompt also explicitly instructs JSON-only output as a
            # fallback, and _strip_json_fence() below cleans up the
            # common case of an open model wrapping its answer in a
            # ```json ... ``` fence despite instructions not to.
            payload["response_format"] = {"type": "json_object"}

        try:
            response = httpx.post(
                ROUTER_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return _strip_json_fence(content) if response_schema is not None else content
        except httpx.TimeoutException as exc:
            raise AppError("AI_PROVIDER_TIMEOUT", "The AI provider timed out.", status_code=504) from exc
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise AppError("AI_PROVIDER_ERROR", f"Hugging Face request failed: {exc}", status_code=502) from exc


def _strip_json_fence(text: str) -> str:
    stripped = _JSON_FENCE.sub("", text.strip())
    # Cheap sanity check only -- the caller (app/agents/intent_schema.py)
    # is responsible for real validation via Pydantic. This just avoids
    # handing obviously-non-JSON text into json.loads unnecessarily.
    try:
        json.loads(stripped)
        return stripped
    except ValueError:
        return text
