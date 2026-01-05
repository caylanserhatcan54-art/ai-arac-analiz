from __future__ import annotations

import json
import os
from typing import Optional
from urllib.request import Request, urlopen


def call_llm_commentary(prompt: str) -> Optional[str]:
    """
    Optional LLM call.
    If env not set, returns None (fallback commentary will be used).
    Uses stdlib urllib to avoid 'requests' dependency.
    """
    endpoint = os.getenv("LLM_ENDPOINT", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()

    if not endpoint:
        return None

    payload = {"prompt": prompt}
    data = json.dumps(payload).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = Request(endpoint, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        # beklenen format: {"text": "..."} veya direkt string
        try:
            j = json.loads(raw)
            if isinstance(j, dict) and "text" in j:
                return str(j["text"])
        except Exception:
            pass
        return raw.strip() if raw.strip() else None
    except Exception:
        return None
