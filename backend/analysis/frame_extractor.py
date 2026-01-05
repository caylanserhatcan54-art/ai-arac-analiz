# backend/analysis/frame_extractor.py
from __future__ import annotations

import os
import uuid
from typing import Dict, Any, List, Optional, Tuple

import cv2


def extract_frames(
    video_path: str,
    out_dir: str,
    *,
    max_frames: int = 36,
    min_gap_sec: float = 0.4,
    target_long_side: int = 1280,
    jpeg_quality: int = 88,
) -> Dict[str, Any]:
    """
    Uniform sampling + basic resize.
    Produces stable set of frames for damage/coverage checks.

    Returns:
      {
        "ok": bool,
        "frames_dir": "...",
        "frames": ["/abs/or/rel/path1.jpg", ...],
        "count": int,
        "message": str
      }
    """
    if not os.path.exists(video_path):
        return {"ok": False, "frames_dir": out_dir, "frames": [], "count": 0, "message": "Video bulunamadı."}

    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"ok": False, "frames_dir": out_dir, "frames": [], "count": 0, "message": "Video açılamadı."}

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    if fps <= 0 or frame_count <= 0:
        # still try sequential read
        fps = 25.0

    duration = frame_count / fps if frame_count else 0.0

    # Determine sampling indices
    if duration <= 0.1:
        stride = 10
        sample_indices = list(range(0, max_frames * stride, stride))
    else:
        # ensure minimum temporal gap to avoid near-duplicates
        gap_frames = max(1, int(min_gap_sec * fps))
        approx = max(1, frame_count // max_frames)
        stride = max(gap_frames, approx)
        sample_indices = list(range(0, frame_count, stride))[:max_frames]

    frames: List[str] = []
    idx_set = set(sample_indices)

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    i = 0
    saved = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if i in idx_set:
            h, w = frame.shape[:2]
            # resize keeping aspect
            long_side = max(w, h)
            if long_side > target_long_side:
                scale = target_long_side / float(long_side)
                new_w = int(w * scale)
                new_h = int(h * scale)
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

            fname = f"frame_{saved:03d}_{uuid.uuid4().hex[:8]}.jpg"
            fpath = os.path.join(out_dir, fname)
            cv2.imwrite(fpath, frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
            frames.append(fpath)
            saved += 1

            if saved >= max_frames:
                break

        i += 1

    cap.release()

    ok = len(frames) >= 8  # below this coverage/damage becomes unreliable
    msg = "Frame çıkarımı tamam." if ok else "Yeterli frame çıkarılamadı; video çok kısa/bozuk olabilir."
    return {"ok": ok, "frames_dir": out_dir, "frames": frames, "count": len(frames), "message": msg}
