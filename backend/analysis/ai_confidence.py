# backend/analysis/ai_confidence.py
from __future__ import annotations

from typing import Dict, Any


def compute_confidence(
    *,
    video_quality: Dict[str, Any],
    coverage: Dict[str, Any],
    damage: Dict[str, Any],
    engine_audio: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Produces a single confidence score (0..100) + explainability.
    This is a "reporting confidence", not "vehicle health confidence".
    """
    v_ok = bool(video_quality.get("ok", False))
    cov_ratio = float(coverage.get("coverage_ratio", 0.0) or 0.0)

    # base
    score = 78.0

    # penalties from quality
    if video_quality.get("too_short"):
        score -= 18
    if video_quality.get("too_low_res"):
        score -= 14
    if video_quality.get("too_dark"):
        score -= 10
    if video_quality.get("too_bright"):
        score -= 8
    if video_quality.get("too_blurry"):
        score -= 16
    if video_quality.get("too_shaky"):
        score -= 10

    # coverage
    if cov_ratio < 0.35:
        score -= 22
    elif cov_ratio < 0.55:
        score -= 12
    elif cov_ratio < 0.70:
        score -= 6

    # engine audio (if present)
    if engine_audio and engine_audio.get("ok") and not engine_audio.get("skipped", False):
        clip = float(engine_audio.get("signals", {}).get("clipping_ratio", 0.0) or 0.0)
        if clip > 0.02:
            score -= 8

    # damage method reliability
    method = str(damage.get("method", "none"))
    if method == "yolo":
        score += 6
    elif method == "heuristic":
        score -= 4
    else:
        score -= 10

    score = max(0.0, min(100.0, score))

    # label
    level = "yüksek"
    if score < 45:
        level = "düşük"
    elif score < 70:
        level = "orta"

    reasons = []
    for h in (video_quality.get("hints") or []):
        reasons.append(h)
    for h in (coverage.get("hints") or []):
        reasons.append(h)
    if engine_audio:
        for h in (engine_audio.get("hints") or []):
            reasons.append(h)

    # keep short
    reasons = reasons[:8]

    return {
        "ok": True,
        "confidence_score": float(round(score, 1)),
        "confidence_level": level,
        "reasons": reasons,
    }
