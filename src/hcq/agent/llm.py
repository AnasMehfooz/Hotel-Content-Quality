"""Chat clients: a local Ollama model, and a scripted stand-in for tests."""

from __future__ import annotations

import copy
from typing import Any, Protocol

import httpx

Message = dict[str, Any]


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    model: str

    def chat(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        schema: dict | None = None,
    ) -> Message:
        """Return the assistant message: {"role": "assistant", "content": str, "tool_calls": [...]}."""
        ...


class OllamaChat:
    """Minimal client for Ollama's /api/chat with tool calling and structured output.

    Defaults suit a 16 GB GPU: a 14B model at Q4 plus a 16k context fits in VRAM.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 300.0,
        temperature: float = 0.0,
        num_ctx: int = 16384,
        think: bool | None = None,
        keep_alive: str = "30m",
        transport: httpx.BaseTransport | None = None,
    ):
        self.model = model
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.think = think
        self.keep_alive = keep_alive
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def chat(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        schema: dict | None = None,
    ) -> Message:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = tools
        if schema:
            payload["format"] = schema
        if self.think is not None:
            payload["think"] = self.think
        try:
            resp = self._client.post("/api/chat", json=payload)
        except httpx.TransportError as exc:
            raise LLMError(
                f"Ollama is not reachable at {self._client.base_url} ({exc}). Is `ollama serve` running?"
            ) from exc
        if resp.status_code == 404:
            raise LLMError(f"Model {self.model!r} is not available. Run: ollama pull {self.model}")
        if resp.status_code >= 400:
            raise LLMError(f"Ollama returned {resp.status_code}: {resp.text[:300]}")
        message = resp.json().get("message") or {}
        message.setdefault("role", "assistant")
        message.setdefault("content", "")
        return message

    def available_models(self) -> list[str]:
        try:
            resp = self._client.get("/api/tags")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama is not reachable at {self._client.base_url}: {exc}") from exc
        return [m["name"] for m in resp.json().get("models", [])]


class ScriptedLLM:
    """Replays scripted assistant messages in order and records every request (for tests)."""

    def __init__(self, responses: list[Message], model: str = "scripted"):
        self.model = model
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[Message],
        *,
        tools: list[dict] | None = None,
        schema: dict | None = None,
    ) -> Message:
        self.calls.append({"messages": copy.deepcopy(messages), "tools": tools, "schema": schema})
        if not self._responses:
            raise LLMError("ScriptedLLM ran out of scripted responses")
        return self._responses.pop(0)
