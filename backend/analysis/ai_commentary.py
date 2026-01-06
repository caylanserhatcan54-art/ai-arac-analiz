from __future__ import annotations
from typing import Dict, Any, List, Optional

from .ai_llm import call_llm_commentary


def _bulletify(items: List[str], max_n: int = 6) -> str:
    items = [x.strip() for x in items if x and x.strip()]
    return "\n".join([f"- {x}" for x in items[:max_n]]) if items else "- (Belirgin uyarı yok)"


def generate_human_commentary(
    *,
    vehicle_type: str,
    scenario: str,
    damage: Dict[str, Any],
    engine_audio: Optional[Dict[str, Any]] = None,
    confidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Fotoğraf + motor sesi bazlı kullanıcı yorumu üretir.
    Video referansı YOKTUR.
    """

    damage_summary = damage.get("summary", {}) or {}
    damage_sev = str(damage_summary.get("severity", "unknown"))

    audio_level = None
    audio_hints = []
    if engine_audio and engine_audio.get("ok") and not engine_audio.get("skipped", False):
        audio_level = str(engine_audio.get("risk_level", "unknown"))
        audio_hints = engine_audio.get("hints") or []

    conf_score = None
    conf_level = None
    conf_reasons = []
    if confidence:
        conf_score = confidence.get("confidence_score")
        conf_level = confidence.get("confidence_level")
        conf_reasons = confidence.get("reasons") or []

    # ================= LLM =================
    prompt = f"""
Sen CARVIX araç ön analiz asistanısın.
Bu rapor sadece FOTOĞRAF ve (varsa) MOTOR SESİ analizine dayanır.
Kesin teşhis iddiası yoktur.

Araç tipi: {vehicle_type}
Kullanım senaryosu: {scenario}

Görsel hasar seviyesi: {damage_sev}
Hasar özeti: {damage_summary}

Motor sesi riski: {audio_level}
Motor sesi ipuçları: {audio_hints}

Güven skoru: {conf_score}
Güven seviyesi: {conf_level}

Çıktı:
- 3–5 cümle genel değerlendirme
- Risk sinyalleri
- Önerilen sonraki adımlar
- Sonunda ekspertiz uyarısı
""".strip()

    llm = call_llm_commentary(prompt)
    if llm:
        return {"ok": True, "method": "llm", "text": llm.strip()}

    # ================= FALLBACK =================
    parts: List[str] = []

    parts.append(
        f"Bu analiz, yüklenen araç fotoğrafları üzerinden yapılan görsel incelemeye dayanır. "
        f"Tespit edilen görsel hasar sinyali seviyesi **{damage_sev.upper()}** olarak değerlendirilmiştir."
    )

    if audio_level:
        parts.append(f"Motor sesi analizinde risk seviyesi **{audio_level.upper()}** olarak işaretlenmiştir.")

    if conf_score is not None and conf_level:
        parts.append(f"Analiz güven seviyesi **{conf_level.upper()}** (Skor: {conf_score}/100).")

    risk_items: List[str] = []

    if damage.get("method") == "yolo":
        labels = damage_summary.get("suspected_labels") or []
        for x in labels[:5]:
            risk_items.append(f"{x['label']} (görülme: {x['count']})")
    else:
        sig = damage_summary.get("signals_avg") or {}
        if sig:
            risk_items.append(
                f"Çizik:{sig.get('scratch_like', 0):.2f} | "
                f"Göçük:{sig.get('dent_like', 0):.2f} | "
                f"Boya:{sig.get('repaint_like', 0):.2f}"
            )

    risk_items.extend(conf_reasons[:3])
    risk_items.extend(audio_hints[:2])

    next_steps = [
        "Şüpheli görünen bölgeleri aracı görerek ve gün ışığında kontrol edin.",
        "Kaput, kapı içleri, direkler ve vida bölgelerini yakından inceleyin.",
        "Satın alma öncesi mutlaka profesyonel ekspertiz yaptırın.",
    ]

    text = (
        "\n".join(parts)
        + "\n\n**Tespit Edilen Risk Sinyalleri**\n"
        + _bulletify(risk_items)
        + "\n\n**Önerilen Sonraki Adımlar**\n"
        + _bulletify(next_steps)
        + "\n\nNot: Bu rapor ekspertiz yerine geçmez; ön bilgilendirme amaçlıdır."
    )

    return {"ok": True, "method": "fallback", "text": text}
