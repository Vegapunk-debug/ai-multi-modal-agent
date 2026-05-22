"""LLM adapter — Groq primary, Gemini fallback.

Wraps streaming + tool-calling + JSON-mode behind one interface so we can swap
providers via env without touching agent code.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from server.config import SETTINGS
from server.observability.tracer import log


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class CompletionDelta:
    text: str = ""
    tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None


class LLM:
    """Provider-agnostic LLM facade. Groq + Gemini implemented; OpenAI compatible."""

    def __init__(
        self,
        provider: str = "groq",
        model: str = "llama-3.3-70b-versatile",
        api_key: str = "",
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        if provider == "groq":
            self.base_url = "https://api.groq.com/openai/v1"
        elif provider == "gemini":
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        temperature: float = 0.6,
        max_tokens: int = 600,
    ) -> str:
        """Non-streaming single-shot."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            if r.status_code != 200:
                log.error("llm.error", status=r.status_code, body=r.text[:500])
                r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"].get("content") or ""

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.6,
        max_tokens: int = 600,
    ) -> AsyncIterator[CompletionDelta]:
        """Streaming completion with tool-call accumulation."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        tool_buffers: dict[int, dict[str, Any]] = {}

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            ) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    log.error("llm.stream_error", status=r.status_code, body=body[:500])
                    r.raise_for_status()

                async for line in r.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if "error" in data:
                        log.error("llm.stream_chunk_error", error=data.get("error"))
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        # Groq sometimes emits keep-alive chunks without choices; skip.
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    text = delta.get("content") or ""
                    finish = choice.get("finish_reason")

                    tcs = delta.get("tool_calls") or []
                    for tc_i, tc in enumerate(tcs):
                        # OpenAI: each chunk has `index` and fragments accumulate.
                        # Gemini: each tool_call arrives whole in a single chunk
                        # without `index`. Default the index to the position.
                        idx = tc.get("index", tc_i)
                        buf = tool_buffers.setdefault(
                            idx,
                            {"id": tc.get("id", ""), "name": "", "arguments": ""},
                        )
                        if tc.get("id"):
                            buf["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            buf["name"] = fn["name"]
                        if fn.get("arguments"):
                            buf["arguments"] += fn["arguments"]

                    completed_calls: list[ToolCall] = []
                    if finish == "tool_calls":
                        for buf in tool_buffers.values():
                            try:
                                args = json.loads(buf["arguments"] or "{}")
                            except json.JSONDecodeError:
                                args = {}
                            completed_calls.append(
                                ToolCall(id=buf["id"], name=buf["name"], arguments=args)
                            )

                    yield CompletionDelta(
                        text=text,
                        tool_calls=completed_calls if completed_calls else None,
                        finish_reason=finish,
                    )


def make_llm() -> LLM:
    """Main agent LLM. Defaults to Gemini 2.5 Flash for best Spanish reasoning
    + native OpenAI-compatible tool calling."""
    if SETTINGS.llm_provider == "groq":
        return LLM(
            provider="groq",
            model=SETTINGS.llm_model if "/" in SETTINGS.llm_model else "meta-llama/llama-4-scout-17b-16e-instruct",
            api_key=SETTINGS.groq_api_key,
        )
    # Gemini default.
    return LLM(
        provider="gemini",
        model=SETTINGS.llm_model if SETTINGS.llm_model.startswith("gemini") else "gemini-2.5-flash",
        api_key=SETTINGS.gemini_api_key,
    )


def make_judge_llm() -> LLM:
    """Grader / doubt-answer LLM. Always Gemini 2.5 Flash if available."""
    if SETTINGS.gemini_api_key:
        return LLM(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key=SETTINGS.gemini_api_key,
        )
    return make_llm()
