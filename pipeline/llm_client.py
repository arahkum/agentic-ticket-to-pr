"""Minimal LLM chat client, OpenAI-compatible.

Default backend: a local Ollama server (http://localhost:11434), so Step 1
works fully offline with no API key and no spend. The corporate network here
blocks GitHub Models (models.github.ai silently returns a fake 200 "OK"), so
local Ollama is the reliable free option; swap to OpenAI/Anthropic later once
you have a key by setting OPENAI_API_KEY (Step 8 covers model routing).
"""
from __future__ import annotations

import os

import requests

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-oss:20b")
# gpt-oss is a reasoning model: it spends tokens on hidden "reasoning" before
# the final answer, so give it headroom or finish_reason="length" cuts it off.
DEFAULT_MAX_TOKENS = 3500


class LLMClientError(RuntimeError):
    pass


def chat_completion(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Send a system+user prompt and return the model's text response."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    except requests.ConnectionError as exc:
        raise LLMClientError(
            "Could not reach Ollama at http://localhost:11434. "
            "Start it with: ollama serve (or open the Ollama app)."
        ) from exc

    if resp.status_code != 200:
        raise LLMClientError(f"LLM call failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    choice = data["choices"][0]
    content = choice["message"].get("content", "")
    if not content and choice.get("finish_reason") == "length":
        raise LLMClientError(
            "Model ran out of tokens before answering (all spent on reasoning). "
            "Increase max_tokens."
        )
    return content
