from __future__ import annotations

import os
from typing import Dict, Any, List
import cv2


def extract_suspicious_frames(
    *,
    token: str,
    damage: Dict[str, Any],
    output_dir: str,
    max_images: int = 5,
) -> List[Dict[str, Any]]:
    """
    Returns list:
    [
      {
        "image_path": "/media/<token>/suspicious/suspicious_1.jpg",
        "caption": "...",
        "severity": "low|medium|high"
      }
    ]
    """
    os.makedirs(output_dir, exist_ok=True)

    results: List[Dict[str, Any]] = []
    method = damage.get("method")

    def to_url(filename: str) -> str:
        return f"/media/{token}/suspicious/{filename}"

    # =========================
    # YOLO BASED
    # =========================
    if method == "yolo":
        findings = damage.get("findings", [])
        findings = sorted(findings, key=lambda x: float(x.get("confidence", 0)), reverse=True)[:max_images]

        for i, f in enumerate(findings):
            frame_path = f.get("frame")
            if not frame_path or not os.path.exists(frame_path):
                continue

            img = cv2.imread(frame_path)
            if img is None:
                continue

            box = f.get("box")
            if box and len(box) == 4:
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)

            filename = f"suspicious_{i+1}.jpg"
            out_path = os.path.join(output_dir, filename)
            cv2.imwrite(out_path, img)

            results.append({
                "image_path": to_url(filename),
                "caption": f"Olası {f.get('label', 'hasar')} sinyali",
                "severity": "medium",
            })

        return results

    # =========================
    # HEURISTIC BASED
    # =========================
    frames = (damage.get("findings", []) or [])[:max_images]

    for i, f in enumerate(frames):
        frame_path = f.get("frame")
        if not frame_path or not os.path.exists(frame_path):
            continue

        img = cv2.imread(frame_path)
        if img is None:
            continue

        filename = f"suspicious_{i+1}.jpg"
        out_path = os.path.join(output_dir, filename)
        cv2.imwrite(out_path, img)

        sig = f.get("signals", {}) or {}
        caption = (
            f"Çizik:{sig.get('scratch_like', 0):.2f} | "
            f"Göçük:{sig.get('dent_like', 0):.2f} | "
            f"Boya:{sig.get('repaint_like', 0):.2f}"
        )

        results.append({
            "image_path": to_url(filename),
            "caption": caption,
            "severity": "medium",
        })

    return results
