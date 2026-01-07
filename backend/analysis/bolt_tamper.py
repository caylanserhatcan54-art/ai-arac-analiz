from __future__ import annotations
from typing import Dict, List, Tuple
import cv2
import numpy as np

def _safe_read(image_path: str):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    return img

def _detect_bolt_like_regions(gray: np.ndarray) -> List[Tuple[int,int,int,int]]:
    """
    Vida/baş benzeri bölgeleri kabaca bulur.
    Bu bir YOLO değil; yakın plan fotoğrafta yeterince iyi çalışır.
    """
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    edges = cv2.Canny(blur, 60, 160)

    # Kapalı konturları bul
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    h, w = gray.shape[:2]
    for c in cnts:
        x,y,bw,bh = cv2.boundingRect(c)
        area = bw*bh
        if area < 120 or area > (h*w*0.12):
            continue
        ar = bw / max(1, bh)
        # Vida başları çoğu zaman karemsi/yuvarlağa yakın
        if 0.55 <= ar <= 1.8:
            boxes.append((x,y,bw,bh))
    # En büyük birkaç tanesini al
    boxes = sorted(boxes, key=lambda b: b[2]*b[3], reverse=True)[:8]
    return boxes

def _tool_mark_score(roi_gray: np.ndarray) -> float:
    """
    Anahtar izi / çizik gibi yüksek frekanslı çizgileri ölçer.
    """
    lap = cv2.Laplacian(roi_gray, cv2.CV_64F)
    energy = float(np.mean(np.abs(lap)))
    return min(1.0, energy / 25.0)

def _paint_crack_score(roi_bgr: np.ndarray) -> float:
    """
    Vida etrafı boya çatlağı/pullanma sinyali: mikro-kontrast ve kenar yoğunluğu
    """
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 160)
    edge_density = float(np.mean(edges > 0))
    return min(1.0, edge_density / 0.18)

def bolt_tamper_assessment(image_path: str) -> Dict[str, object]:
    """
    Sök-tak ihtimali: anahtar izi + boya çatlağı + düzensiz doku
    Çıkış:
      - label: DETECTED / SUSPECTED / INSUFFICIENT_EVIDENCE
      - score 0..1
    """
    img = _safe_read(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    boxes = _detect_bolt_like_regions(gray)
    if not boxes:
        return {
            "label": "INSUFFICIENT_EVIDENCE",
            "score": 0.0,
            "reason": "Vida/baş benzeri bölge tespit edilemedi (daha yakın/net çekim gerekli).",
            "bolts": []
        }

    bolt_reports = []
    scores = []
    h, w = gray.shape[:2]

    for (x,y,bw,bh) in boxes:
        pad = int(max(bw, bh) * 0.25)
        x1 = max(0, x - pad); y1 = max(0, y - pad)
        x2 = min(w, x + bw + pad); y2 = min(h, y + bh + pad)

        roi = img[y1:y2, x1:x2]
        roi_g = gray[y1:y2, x1:x2]

        tool = _tool_mark_score(roi_g)
        crack = _paint_crack_score(roi)

        # birleşik skor
        s = 0.60 * tool + 0.40 * crack
        s = float(max(0.0, min(1.0, s)))
        scores.append(s)

        bolt_reports.append({
            "box": [int(x1), int(y1), int(x2), int(y2)],
            "tool_mark": tool,
            "paint_crack": crack,
            "score": s
        })

    # En güçlü 2 vida üzerinden karar
    top = sorted(scores, reverse=True)[:2]
    final = float(sum(top) / max(1, len(top)))

    if final >= 0.80:
        label = "DETECTED"
        reason = "Vida/menteşe bölgesinde anahtar izi ve boya çatlağı güçlü."
    elif final >= 0.62:
        label = "SUSPECTED"
        reason = "Sök-tak şüphesi var, kanıt orta (daha net yakın çekim önerilir)."
    else:
        label = "INSUFFICIENT_EVIDENCE"
        reason = "Sök-tak için yeterli kanıt yok."

    return {"label": label, "score": final, "reason": reason, "bolts": bolt_reports}
