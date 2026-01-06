from __future__ import annotations
from typing import Dict, Any


def compute_confidence(
    *,
    image_count: int,
    damage: Dict[str, Any],
    engine_audio: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Rapor güven skoru (0–100).
    Araç durumu değil, analiz güveni ölçülür.
    """

    score = 80.0
    reasons = []

    # Fotoğraf sayısı
    if image_count < 4:
        score -= 25
        reasons.append("Fotoğraf sayısı çok az.")
    elif image_count < 8:
        score -= 12
        reasons.append("Fotoğraf sayısı sınırlı.")
    elif image_count >= 12:
        score += 5

    # Hasar yöntemi
    method = damage.get("method")
    if method == "yolo":
        score += 6
    elif method == "heuristic":
        score -= 4
    else:
        score -= 10
        reasons.append("Hasar analizi sınırlı.")

    # Motor sesi (opsiyonel)
    if engine_audio and engine_audio.get("ok") and not engine_audio.get("skipped"):
        clip = engine_audio.get("signals", {}).get("clipping_ratio", 0.0)
        if clip and clip > 0.02:
            score -= 8
            reasons.append("Motor sesi kaydı patlamalı (clipping).")

    score = max(0.0, min(100.0, score))

    level = "yüksek"
    if score < 45:
        level = "düşük"
    elif score < 70:
        level = "orta"

    return {
        "ok": True,
        "confidence_score": round(score, 1),
        "confidence_level": level,
        "reasons": reasons[:6],
    }
