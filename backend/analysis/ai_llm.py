# backend/analysis/ai_llm.py
from __future__ import annotations

import os
from typing import Dict, Any, Optional

import requests


def call_llm_commentary(prompt: str, *, timeout_sec: int = 25) -> Optional[str]:
    """
    Optional LLM call.
    - Uses OPENAI_API_KEY if present.
    - If not present or fails: returns None (caller uses fallback).
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    # Minimal request: OpenAI Responses API (HTTP)
    # Eğer endpoint/format değiştiyse: yine de None fallback’le çalışır.
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": prompt,
        "temperature": 0.4,
        "max_output_tokens": 420,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
        if r.status_code >= 300:
            return None
        data = r.json()
        # Try to extract text in a robust way
        if "output_text" in data and isinstance(data["output_text"], str):
            return data["output_text"].strip() or None
        # fallback parsing
        out = data.get("output", [])
        if isinstance(out, list) and out:
            # search for text
            texts = []
            for item in out:
                content = item.get("content", [])
                for c in content:
                    if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                        texts.append(c["text"])
            txt = "\n".join(texts).strip()
            return txt or None
        return None
    except Exception:
        return None
