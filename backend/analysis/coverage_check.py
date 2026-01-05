# backend/analysis/coverage_check.py
from __future__ import annotations

import os
from typing import Dict, Any, List

import cv2
import numpy as np


def estimate_coverage(frame_paths: List[str], *, grid: int = 6) -> Dict[str, Any]:
    """
    Very practical coverage estimator:
    - divides frame into grid, tracks motion presence across frames
    - if user only records same spot, coverage is low
    Not perfect, but reliable enough as UX guidance.
    """
    frame_paths = [p for p in frame_paths if os.path.exists(p)]
    if len(frame_paths) < 6:
        return {"ok": False, "coverage_ratio": 0.0, "message": "Kapsama analizi için yeterli frame yok.", "hints": ["Aracı daha geniş açıyla ve çevresini dolaşarak çekin."]}

    prev = None
    H = W = None
    visited = np.zeros((grid, grid), dtype=np.float32)

    for fp in frame_paths:
        img = cv2.imread(fp)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if prev is not None:
            diff = cv2.absdiff(prev, gray)
            _, th = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
            th = cv2.medianBlur(th, 5)

            h, w = th.shape[:2]
            H, W = h, w
            gh = h // grid
            gw = w // grid
            for r in range(grid):
                for c in range(grid):
                    y1 = r * gh
                    y2 = (r + 1) * gh if r < grid - 1 else h
                    x1 = c * gw
                    x2 = (c + 1) * gw if c < grid - 1 else w
                    cell = th[y1:y2, x1:x2]
                    if cell.size == 0:
                        continue
                    if float(np.mean(cell > 0)) > 0.03:
                        visited[r, c] += 1.0

        prev = gray

    # Normalize
    if visited.sum() <= 0:
        return {
            "ok": True,
            "coverage_ratio": 0.20,
            "message": "Kapsama düşük görünüyor.",
            "hints": ["Aracın etrafında dolaşarak 360° çekim yapın, her paneli ayrı ayrı gösterin."],
        }

    visited_norm = visited > 0
    coverage_ratio = float(np.mean(visited_norm))

    hints: List[str] = []
    if coverage_ratio < 0.45:
        hints.append("Kapsama düşük: Aracın ön/yan/arka panellerini ayrı ayrı gösterin (360°).")
        hints.append("Çok hızlı geçmeyin: her panelde 1–2 sn bekleyin.")
    elif coverage_ratio < 0.65:
        hints.append("Kapsama orta: Çamurluklar, kapı altları, tampon köşeleri ve tavanı da gösterin.")
    else:
        hints.append("Kapsama iyi: Analiz doğruluğu için yeterli görüntü var.")

    return {
        "ok": True,
        "coverage_ratio": coverage_ratio,
        "message": "Kapsama analizi tamam.",
        "hints": hints,
    }
