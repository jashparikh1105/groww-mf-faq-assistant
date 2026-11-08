"""LLM client. Groq by default; OpenAI / Gemini / Mistral (OpenAI-compatible) and Anthropic optional.

Provider and model are read from .env (LLM_PROVIDER, GROQ_MODEL, ...).
If the main Groq model fails (e.g. a preview model was retired) we retry with GROQ_FALLBACK_MODEL.
"""
from __future__ import annotations

import re

import httpx

from src.config import env, get_config

OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "GROQ_MODEL", "qwen/qwen3.8-27b"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt-4o-mini"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "GEMINI_MODEL", "gemini-2.5-flash"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "MISTRAL_MODEL", "mistral-small-latest"),
}

THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


class LLMUnavailable(Exception):
    pass


def provider() -> str:
    return env("LLM_PROVIDER", "groq").lower()


def is_configured() -> bool:
    p = provider()
    if p == "anthropic":
        return bool(env("ANTHROPIC_API_KEY"))
    return p in OPENAI_COMPATIBLE and bool(env(OPENAI_COMPATIBLE[p][1]))


def model_name() -> str:
    p = provider()
    if p == "anthropic":
        return env("ANTHROPIC_MODEL", "claude-haiku-4-5")
    base, key_var, model_var, default = OPENAI_COMPATIBLE.get(p, OPENAI_COMPATIBLE["groq"])
    return env(model_var, default)


def _clean(text: str) -> str:
    text = THINK_RE.sub("", text or "")
    text = re.sub(r"^.*?</think>", "", text, flags=re.S)  # unmatched closing tag
    return text.strip()


def _openai_chat(base: str, key: str, model: str, system: str, user: str, extra: dict | None) -> str:
    cfg = get_config()["llm"]
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
    }
    if extra:
        body.update(extra)
    r = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=cfg["timeout_seconds"],
    )
    if r.status_code == 400 and extra:  # model does not accept the extra params -> retry plain
        return _openai_chat(base, key, model, system, user, None)
    r.raise_for_status()
    return _clean(r.json()["choices"][0]["message"].get("content") or "")


def _anthropic_chat(system: str, user: str) -> str:
    cfg = get_config()["llm"]
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": env("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model_name(), "max_tokens": cfg["max_tokens"], "temperature": cfg["temperature"],
              "system": system, "messages": [{"role": "user", "content": user}]},
        timeout=cfg["timeout_seconds"],
    )
    r.raise_for_status()
    return _clean("".join(b.get("text", "") for b in r.json().get("content", [])))


def generate(system: str, user: str) -> tuple[str, str]:
    """Return (text, model_used). Raises LLMUnavailable if nothing works."""
    if not is_configured():
        raise LLMUnavailable("no API key configured")
    p = provider()
    try:
        if p == "anthropic":
            return _anthropic_chat(system, user), model_name()
        base, key_var, model_var, default = OPENAI_COMPATIBLE[p]
        key = env(key_var)
        models = [env(model_var, default)]
        if p == "groq" and env("GROQ_FALLBACK_MODEL"):
            models.append(env("GROQ_FALLBACK_MODEL"))
        last_err: Exception | None = None
        for m in models:
            extra = {"reasoning_format": "hidden"} if (p == "groq" and "qwen" in m) else None
            try:
                return _openai_chat(base, key, m, system, user, extra), m
            except (httpx.HTTPError, KeyError, ValueError) as e:
                last_err = e
        raise LLMUnavailable(str(last_err))
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise LLMUnavailable(str(e)) from e
