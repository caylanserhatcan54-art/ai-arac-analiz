from __future__ import annotations

import os
from typing import Dict, Any, List
import cv2


def extract_suspicious_frames_from_images(
    *,
    token: str,
    damage: Dict[str, Any],
    output_dir: str,
    max_images: int = 4,
) -> List[Dict[str, Any]]:
    """
    Selects suspicious images from damage pipeline output and saves thumbnails.

    Returns list:
    [
      {"image_path": "...jpg", "caption": "...", "severity": "low|medium|high"}
    ]
    """
    os.makedirs(output_dir, exist_ok=True)
    results: List[Dict[str, Any]] = []

    method = damage.get("method")

    # YOLO BASED: findings contain {"frame": <path>, "label", "confidence", "box"}
    if method == "yolo":
        findings = (damage.get("findings") or [])
        findings = sorted(findings, key=lambda x: float(x.get("confidence", 0)), reverse=True)[:max_images]

        for i, f in enumerate(findings):
            img_path = f.get("frame")
            if not img_path or not os.path.exists(img_path):
                continue

            img = cv2.imread(img_path)
            if img is None:
                continue

            box = f.get("box")
            if box and len(box) == 4:
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)

            out_path = os.path.join(output_dir, f"suspicious_{i+1}.jpg")
            cv2.imwrite(out_path, img)

            results.append({
                "image_path": out_path,
                "caption": f"Olası {f.get('label', 'hasar')} sinyali",
                "severity": "medium",
            })

        return results

    # HEURISTIC BASED: findings contain {"frame": <path>, "signals": {...}}
    frames = (damage.get("findings") or [])[:max_images]

    for i, f in enumerate(frames):
        img_path = f.get("frame")
        if not img_path or not os.path.exists(img_path):
            continue

        img = cv2.imread(img_path)
        if img is None:
            continue

        out_path = os.path.join(output_dir, f"suspicious_{i+1}.jpg")
        cv2.imwrite(out_path, img)

        sig = f.get("signals", {}) or {}
        caption = (
            f"Çizik:{sig.get('scratch_like', 0):.2f} | "
            f"Göçük:{sig.get('dent_like', 0):.2f} | "
            f"Boya:{sig.get('repaint_like', 0):.2f}"
        )

        results.append({
            "image_path": out_path,
            "caption": caption,
            "severity": "medium",
        })

    return results
