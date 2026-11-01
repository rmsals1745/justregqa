"""Optional LLM backends, stdlib only. Keys come from the environment — never from code."""
from __future__ import annotations

import json
import os
import urllib.request


class LLMError(RuntimeError):
    pass


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (does not override variables already set)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def backend() -> str:
    return os.environ.get("REGQA_LLM", "none").strip().lower() or "none"


def _post(url: str, headers: dict, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as r:   # no artificial timeout: long answers are fine
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def _need(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise LLMError(f"{name} is not set (see .env.example)")
    return v


def complete(system: str, user: str) -> str:
    kind = backend()
    if kind == "anthropic":
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": _need("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
             "content-type": "application/json"},
            {"model": _need("REGQA_ANTHROPIC_MODEL"), "max_tokens": 1024, "system": system,
             "messages": [{"role": "user", "content": user}]},
        )
        return "".join(b.get("text", "") for b in data.get("content", []))
    if kind == "openai":
        base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        data = _post(
            f"{base}/chat/completions",
            {"authorization": f"Bearer {_need('OPENAI_API_KEY')}", "content-type": "application/json"},
            {"model": _need("REGQA_OPENAI_MODEL"),
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        return data["choices"][0]["message"]["content"]
    raise LLMError(f"unknown REGQA_LLM backend: {kind!r}")
