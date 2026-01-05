from __future__ import annotations

import os
from typing import Dict, Any, List, Optional

import cv2
import numpy as np

from .live_yolo import YoloDetector, DEFAULT_DAMAGE_LABELS


def _heuristic_damage_signals(image_bgr: np.ndarray) -> Dict[str, float]:
    """
    Conservative heuristic signals to avoid false positives.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    edges = cv2.Canny(gray, 80, 180)
    edge_density = float(np.mean(edges > 0))

    lap = cv2.Laplacian(gray, cv2.CV_64F)
    lap_var = float(lap.var())

    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    sat_std = float(np.std(hsv[:, :, 1]))
    val_std = float(np.std(hsv[:, :, 2]))

    scratch_like = np.clip((edge_density - 0.05) / 0.08, 0.0, 1.0)
    dent_like = np.clip((lap_var - 220.0) / 900.0, 0.0, 1.0)
    repaint_like = np.clip((sat_std - 45.0) / 80.0, 0.0, 1.0)

    return {
        "scratch_like": float(scratch_like),
        "dent_like": float(dent_like),
        "repaint_like": float(repaint_like),
    }


def run_damage_pipeline(
    frame_paths: List[str],
    *,
    vehicle_type: str = "car",
    yolo_model_path: Optional[str] = None,
    yolo_conf: float = 0.30,
    yolo_iou: float = 0.45,
    max_frames_to_process: int = 18,
) -> Dict[str, Any]:
    """
    Damage analysis pipeline (product-safe).
    """

    frame_paths = [p for p in frame_paths if os.path.exists(p)]
    if not frame_paths:
        return {"ok": False, "method": "none", "summary": {}, "findings": []}

    # ----------------------------
    # HEURISTIC PRE-SCREEN
    # ----------------------------
    scored_frames = []

    for fp in frame_paths:
        img = cv2.imread(fp)
        if img is None:
            continue
        sig = _heuristic_damage_signals(img)
        score = (
            0.45 * sig["scratch_like"]
            + 0.35 * sig["dent_like"]
            + 0.20 * sig["repaint_like"]
        )
        scored_frames.append((fp, sig, score))

    scored_frames.sort(key=lambda x: x[2], reverse=True)
    top_frames = scored_frames[:max_frames_to_process]

    # ----------------------------
    # TRY YOLO (IF AVAILABLE)
    # ----------------------------
    detector = None
    use_yolo = False

    if yolo_model_path:
        try:
            detector = YoloDetector(yolo_model_path)
            use_yolo = True
        except Exception:
            use_yolo = False

    findings: List[Dict[str, Any]] = []
    label_counter: Dict[str, int] = {}

    if use_yolo and detector:
        for fp, _, _ in top_frames:
            dets = detector.predict(fp, conf=yolo_conf, iou=yolo_iou)
            for d in dets:
                lbl = str(d.get("label", "unknown")).lower()
                conf = float(d.get("conf", 0.0))
                if conf < yolo_conf:
                    continue

                label_counter[lbl] = label_counter.get(lbl, 0) + 1

                findings.append({
                    "frame": fp,
                    "label": lbl,
                    "confidence": conf,
                })

        suspected = [
            {"label": k, "count": v}
            for k, v in label_counter.items()
            if k in DEFAULT_DAMAGE_LABELS
        ]

        severity = "low"
        total = sum(x["count"] for x in suspected)
        if total >= 6:
            severity = "high"
        elif total >= 3:
            severity = "medium"

        return {
            "ok": True,
            "method": "yolo",
            "summary": {
                "severity": severity,
                "suspected_labels": suspected[:5],
            },
            "findings": findings[:20],
        }

    # ----------------------------
    # FALLBACK: HEURISTIC ONLY
    # ----------------------------
    avg_score = float(np.mean([x[2] for x in top_frames])) if top_frames else 0.0

    severity = "low"
    if avg_score >= 0.60:
        severity = "high"
    elif avg_score >= 0.40:
        severity = "medium"

    findings = [
        {
            "frame": fp,
            "signals": sig,
            "score": sc,
        }
        for fp, sig, sc in top_frames[:6]
        if sc >= 0.35
    ]

    return {
        "ok": True,
        "method": "heuristic",
        "summary": {
            "severity": severity,
            "score": avg_score,
        },
        "findings": findings,
    }
