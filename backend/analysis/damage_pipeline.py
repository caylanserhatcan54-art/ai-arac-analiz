# backend/analysis/damage_pipeline.py
from __future__ import annotations

import os
import math
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from .live_yolo import YoloDetector, DEFAULT_DAMAGE_LABELS


def _heuristic_damage_signals(image_bgr: np.ndarray) -> Dict[str, float]:
    """
    Heuristic signals (works without ML):
    - edge density anomalies (scratches/cracks)
    - local contrast anomalies
    - color inconsistency patches (repaint-ish)
    Returns normalized-ish scores 0..1
    """
    h, w = image_bgr.shape[:2]
    if h < 10 or w < 10:
        return {"scratch_like": 0.0, "dent_like": 0.0, "repaint_like": 0.0}

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # edges
    edges = cv2.Canny(gray, 60, 160)
    edge_density = float(np.mean(edges > 0))  # 0..1

    # texture / contrast
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    lap_var = float(lap.var())

    # repaint-ish: HSV saturation/value variance differences
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    sat_std = float(np.std(sat))
    val_std = float(np.std(val))

    # Normalize with soft ranges (keep conservative)
    scratch_like = np.clip((edge_density - 0.03) / 0.10, 0.0, 1.0)  # edges unusually high
    dent_like = np.clip((lap_var - 150.0) / 900.0, 0.0, 1.0)        # strong local curvature/contrast
    repaint_like = np.clip((sat_std - 30.0) / 70.0, 0.0, 1.0) * 0.6 + np.clip((val_std - 35.0) / 80.0, 0.0, 1.0) * 0.4
    repaint_like = float(np.clip(repaint_like, 0.0, 1.0))

    return {
        "scratch_like": float(scratch_like),
        "dent_like": float(dent_like),
        "repaint_like": repaint_like,
    }


def run_damage_pipeline(
    frame_paths: List[str],
    *,
    vehicle_type: str = "car",
    yolo_model_path: Optional[str] = None,
    yolo_conf: float = 0.25,
    yolo_iou: float = 0.45,
    max_frames_to_process: int = 28,
) -> Dict[str, Any]:
    """
    Damage inference:
    - If YOLO model available: use detections
    - Else: heuristic signals from frames

    Returns product-safe structured output.
    """
    frame_paths = [p for p in frame_paths if os.path.exists(p)]
    if not frame_paths:
        return {
            "ok": False,
            "message": "Hasar analizi için frame bulunamadı.",
            "method": "none",
            "summary": {},
            "findings": [],
        }

    use_yolo = False
    detector: Optional[YoloDetector] = None
    if yolo_model_path:
        try:
            detector = YoloDetector(yolo_model_path)
            use_yolo = True
        except Exception:
            use_yolo = False
            detector = None

    findings: List[Dict[str, Any]] = []

    frames_to_process = frame_paths[:max_frames_to_process]

    if use_yolo and detector is not None:
        # YOLO-based
        label_counts: Dict[str, int] = {}
        top_conf: float = 0.0

        for fp in frames_to_process:
            dets = detector.predict(fp, conf=yolo_conf, iou=yolo_iou)
            for d in dets:
                label = str(d.get("label", "unknown"))
                conf = float(d.get("conf", 0.0))
                top_conf = max(top_conf, conf)
                label_counts[label] = label_counts.get(label, 0) + 1
                # keep a few representative detections
                if conf >= max(0.45, yolo_conf):
                    findings.append({"frame": fp, "type": "yolo", "label": label, "confidence": conf, "box": d.get("box")})

        # Interpret
        suspected = []
        for lbl, cnt in sorted(label_counts.items(), key=lambda x: x[1], reverse=True):
            if lbl.lower() in DEFAULT_DAMAGE_LABELS or any(k in lbl.lower() for k in ["scratch", "dent", "crack", "broken", "damage", "paint"]):
                suspected.append({"label": lbl, "count": cnt})

        severity = "low"
        if sum([x["count"] for x in suspected]) >= 6 or top_conf >= 0.75:
            severity = "high"
        elif sum([x["count"] for x in suspected]) >= 3 or top_conf >= 0.60:
            severity = "medium"

        return {
            "ok": True,
            "message": "Hasar analizi tamam (YOLO).",
            "method": "yolo",
            "summary": {
                "severity": severity,
                "top_confidence": float(top_conf),
                "suspected_labels": suspected[:6],
            },
            "findings": findings[:40],
        }

    # Heuristic-based
    agg = {"scratch_like": 0.0, "dent_like": 0.0, "repaint_like": 0.0}
    per_frame: List[Dict[str, Any]] = []

    for fp in frames_to_process:
        img = cv2.imread(fp)
        if img is None:
            continue
        sig = _heuristic_damage_signals(img)
        per_frame.append({"frame": fp, "signals": sig})
        for k in agg:
            agg[k] += float(sig.get(k, 0.0))

    n = max(1, len(per_frame))
    for k in agg:
        agg[k] /= n

    # severity heuristic
    score = float(0.45 * agg["scratch_like"] + 0.35 * agg["dent_like"] + 0.20 * agg["repaint_like"])
    severity = "low"
    if score >= 0.62:
        severity = "high"
    elif score >= 0.42:
        severity = "medium"

    # Keep only notable frames
    notable = sorted(
        per_frame,
        key=lambda x: float(0.45 * x["signals"]["scratch_like"] + 0.35 * x["signals"]["dent_like"] + 0.20 * x["signals"]["repaint_like"]),
        reverse=True,
    )[:10]

    return {
        "ok": True,
        "message": "Hasar analizi tamam (heuristic).",
        "method": "heuristic",
        "summary": {
            "severity": severity,
            "score": score,
            "signals_avg": agg,
        },
        "findings": notable,
    }
