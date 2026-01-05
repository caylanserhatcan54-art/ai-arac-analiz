# backend/analysis/suspicious_frames.py
from __future__ import annotations

import os
from typing import Dict, Any, List

import cv2


def extract_suspicious_frames(
    *,
    token: str,
    damage: Dict[str, Any],
    output_dir: str,
    max_images: int = 4,
) -> List[Dict[str, Any]]:
    """
    Extracts representative suspicious frames for frontend display.

    Returns:
    [
      {
        "image_path": "/analysis_frames/<token>/suspicious/suspicious_1.jpg",
        "caption": "...",
        "severity": "low|medium|high"
      }
    ]
    """

    os.makedirs(output_dir, exist_ok=True)
    results: List[Dict[str, Any]] = []

    method = damage.get("method")
    severity = damage.get("summary", {}).get("severity", "medium")

    # Frontend için PUBLIC path prefix
    public_prefix = f"/analysis_frames/{token}/suspicious"

    # =========================
    # YOLO BASED
    # =========================
    if method == "yolo":
        findings = damage.get("findings", [])
        findings = sorted(
            findings,
            key=lambda x: float(x.get("confidence", 0.0)),
            reverse=True,
        )[:max_images]

        for i, f in enumerate(findings):
            frame_path = f.get("frame")
            if not frame_path or not os.path.exists(frame_path):
                continue

            img = cv2.imread(frame_path)
            if img is None:
                continue

            out_name = f"suspicious_{i+1}.jpg"
            out_path = os.path.join(output_dir, out_name)
            cv2.imwrite(out_path, img)

            results.append({
                "image_path": f"{public_prefix}/{out_name}",
                "caption": f"Olası {f.get('label', 'hasar')} sinyali",
                "severity": severity,
            })

        return results

    # =========================
    # HEURISTIC BASED
    # =========================
    frames = damage.get("findings", [])[:max_images]

    for i, f in enumerate(frames):
        frame_path = f.get("frame")
        if not frame_path or not os.path.exists(frame_path):
            continue

        img = cv2.imread(frame_path)
        if img is None:
            continue

        out_name = f"suspicious_{i+1}.jpg"
        out_path = os.path.join(output_dir, out_name)
        cv2.imwrite(out_path, img)

        sig = f.get("signals", {})
        caption = (
            f"Çizik: {sig.get('scratch_like', 0):.2f} · "
            f"Göçük: {sig.get('dent_like', 0):.2f} · "
            f"Boya: {sig.get('repaint_like', 0):.2f}"
        )

        results.append({
            "image_path": f"{public_prefix}/{out_name}",
            "caption": caption,
            "severity": severity,
        })

    return results
