from __future__ import annotations
from typing import Dict, Tuple
import cv2
import numpy as np

def _safe_read(image_path: str):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    return img

def _panel_consistency_features(img_bgr: np.ndarray) -> Dict[str, float]:
    """
    Boya/lokal boya sinyalleri için basit ama stabil feature seti.
    Yaklaşım:
    - Lab uzayında panel içi renk dağılımı (std)
    - Kenar bölgelerinde overspray ihtimali (edge band variance)
    - Doku (L kanalında high-frequency energy)
    """
    h, w = img_bgr.shape[:2]
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # Panel içi renk std (lokal boya -> panel içinde anormal std)
    a_std = float(np.std(A))
    b_std = float(np.std(B))
    l_std = float(np.std(L))

    # High-frequency energy (doku farkı / zımpara / portakal)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    hf_energy = float(np.mean(np.abs(lap)))

    # Kenar bandı analizi (overspray/maskeleme çoğu kenarlarda iz bırakır)
    band = int(max(6, min(h, w) * 0.06))
    top = lab[:band, :, :]
    bottom = lab[h-band:h, :, :]
    left = lab[:, :band, :]
    right = lab[:, w-band:w, :]
    edge_pixels = np.concatenate([top.reshape(-1,3), bottom.reshape(-1,3), left.reshape(-1,3), right.reshape(-1,3)], axis=0)
    center_pixels = lab[band:h-band, band:w-band, :].reshape(-1,3) if (h > 2*band and w > 2*band) else lab.reshape(-1,3)

    edge_std = float(np.std(edge_pixels[:,0])) + float(np.std(edge_pixels[:,1])) + float(np.std(edge_pixels[:,2]))
    center_std = float(np.std(center_pixels[:,0])) + float(np.std(center_pixels[:,1])) + float(np.std(center_pixels[:,2]))
    edge_vs_center = float(edge_std - center_std)

    return {
        "l_std": l_std,
        "a_std": a_std,
        "b_std": b_std,
        "hf_energy": hf_energy,
        "edge_vs_center": edge_vs_center,
    }

def paint_local_repair_score(image_path: str) -> Dict[str, object]:
    """
    Output:
      - label: DETECTED / SUSPECTED / INSUFFICIENT_EVIDENCE
      - score: 0..1
      - reason: kısa açıklama
    Uydurmamak için: skor düşükse 'INSUFFICIENT_EVIDENCE'.
    """
    img = _safe_read(image_path)
    feats = _panel_consistency_features(img)

    # Skorlama (heuristic) — sonradan veriyle kalibre edilebilir.
    # Lokal boya çoğu zaman panel içi renk/doku tutarsızlığını artırır.
    score = 0.0
    score += min(1.0, feats["a_std"] / 12.0) * 0.22
    score += min(1.0, feats["b_std"] / 12.0) * 0.22
    score += min(1.0, feats["hf_energy"] / 18.0) * 0.30
    score += min(1.0, max(0.0, feats["edge_vs_center"]) / 25.0) * 0.26

    score = float(max(0.0, min(1.0, score)))

    # 3 seviyeli karar (uydurmama)
    if score >= 0.78:
        return {"label": "DETECTED", "score": score, "reason": "Panel içinde renk/doku tutarsızlığı güçlü.", "features": feats}
    if score >= 0.62:
        return {"label": "SUSPECTED", "score": score, "reason": "Lokal boya/sonradan işlem şüphesi var, kanıt orta.", "features": feats}
    return {"label": "INSUFFICIENT_EVIDENCE", "score": score, "reason": "Boya/lokal boya için yeterli kanıt yok.", "features": feats}
