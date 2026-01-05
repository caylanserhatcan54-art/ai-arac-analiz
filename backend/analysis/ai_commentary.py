# backend/analysis/ai_commentary.py
from __future__ import annotations

from typing import Dict, Any, List, Optional

from .ai_llm import call_llm_commentary


def _bulletify(items: List[str], max_n: int = 6) -> str:
    items = [x.strip() for x in items if x and x.strip()]
    items = items[:max_n]
    return "\n".join([f"- {x}" for x in items]) if items else "- (Belirgin uyarı yok)"


def generate_human_commentary(
    *,
    vehicle_type: str,
    scenario: str,
    video_quality: Dict[str, Any],
    coverage: Dict[str, Any],
    damage: Dict[str, Any],
    engine_audio: Optional[Dict[str, Any]] = None,
    confidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Produces a user-facing commentary block.
    Uses LLM if configured; otherwise produces deterministic product copy.
    """
    v_hints = list(video_quality.get("hints") or [])
    c_hints = list(coverage.get("hints") or [])
    e_hints = list((engine_audio or {}).get("hints") or [])

    damage_summary = damage.get("summary", {}) or {}
    damage_sev = str(damage_summary.get("severity", "unknown"))

    audio_level = None
    if engine_audio and engine_audio.get("ok") and not engine_audio.get("skipped", False):
        audio_level = str(engine_audio.get("risk_level", "unknown"))

    conf_score = None
    conf_level = None
    if confidence:
        conf_score = confidence.get("confidence_score")
        conf_level = confidence.get("confidence_level")

    prompt = f"""
Sen CARVIX araç ön-analiz asistanısın. Kullanıcıya "ekspertiz yerine geçmez" uyarısı ile profesyonel, anlaşılır ve satışa uygun bir rapor yorumu yaz.
Kısa, net, kanıt temelli konuş. Kesin teşhis iddiası yok. Kullanıcıya bir sonraki adımları öner.

Araç tipi: {vehicle_type}
Senaryo: {scenario}

Video kalite:
- ok: {video_quality.get("ok")}
- süre(sn): {video_quality.get("duration_sec")}
- çözünürlük: {video_quality.get("width")}x{video_quality.get("height")}
- hints: {v_hints}

Kapsama:
- coverage_ratio: {coverage.get("coverage_ratio")}
- hints: {c_hints}

Görsel hasar:
- method: {damage.get("method")}
- severity: {damage_sev}
- summary: {damage_summary}

Motor sesi:
- risk: {audio_level}
- hints: {e_hints}

Güven skoru:
- score: {conf_score}
- level: {conf_level}

Çıktı formatı:
1) 3-5 cümlelik genel değerlendirme
2) "Tespit Edilen Risk Sinyalleri" altında maddeler
3) "Önerilen Sonraki Adımlar" altında maddeler
4) Sonda tek satır: "Not: Bu rapor ekspertiz yerine geçmez; ön bilgilendirme amaçlıdır."
""".strip()

    llm = call_llm_commentary(prompt)
    if llm:
        return {"ok": True, "method": "llm", "text": llm.strip()}

    # Fallback deterministic
    parts: List[str] = []
    parts.append(
        f"Bu ön analiz, {vehicle_type} için yüklenen video üzerinden görsel risk sinyallerini çıkarır ve (uygunsa) motor sesi için ek risk değerlendirmesi üretir. "
        f"Görsel hasar sinyali seviyesi: **{damage_sev.upper()}**."
    )
    if audio_level:
        parts.append(f"Motor sesi risk seviyesi: **{audio_level.upper()}** (kesin teşhis değildir).")
    if conf_score is not None and conf_level:
        parts.append(f"Rapor güveni: **{conf_level.upper()}** (Skor: {conf_score}/100).")

    risk_bullets: List[str] = []
    if damage.get("method") == "yolo":
        labels = (damage.get("summary", {}).get("suspected_labels") or [])[:5]
        if labels:
            risk_bullets.append("Modelin işaretlediği olası bölgeler: " + ", ".join([f"{x['label']} (x{x['count']})" for x in labels]))
    else:
        sig = (damage.get("summary", {}).get("signals_avg") or {})
        if sig:
            risk_bullets.append(f"Çizik benzeri sinyal: {sig.get('scratch_like', 0):.2f} | Göçük benzeri sinyal: {sig.get('dent_like', 0):.2f} | Boya/ton tutarsızlığı: {sig.get('repaint_like', 0):.2f}")

    if v_hints:
        risk_bullets.extend(v_hints[:3])
    if c_hints:
        risk_bullets.extend(c_hints[:3])
    if e_hints:
        risk_bullets.extend(e_hints[:2])

    next_steps = [
        "Şüpheli bölgeleri araca gidince gün ışığında yakın plan kontrol edin (kapı altı, tampon köşesi, çamurluk, tavan).",
        "Kaput açıkken 5–10 sn rölanti sesi kaydı alın (içten yanmalı araçlarda).",
        "Satın alma öncesi mutlaka profesyonel ekspertiz ve OBD/şasi kontrolü yaptırın.",
    ]

    text = (
        "\n".join(parts)
        + "\n\n**Tespit Edilen Risk Sinyalleri**\n"
        + _bulletify(risk_bullets, max_n=8)
        + "\n\n**Önerilen Sonraki Adımlar**\n"
        + _bulletify(next_steps, max_n=6)
        + "\n\nNot: Bu rapor ekspertiz yerine geçmez; ön bilgilendirme amaçlıdır."
    )
    return {"ok": True, "method": "fallback", "text": text}
