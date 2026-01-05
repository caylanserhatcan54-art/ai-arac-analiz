# backend/analysis/video_quality.py
from __future__ import annotations

import os
import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List, Tuple

import cv2
import numpy as np


@dataclass
class VideoQualityResult:
    ok: bool
    message: str
    duration_sec: float
    fps: float
    width: int
    height: int
    frame_count: int

    # Quality signals
    blur_score_mean: float
    blur_score_p10: float
    exposure_mean: float
    exposure_p10: float
    exposure_p90: float
    shake_score: float  # higher = more shake
    motion_score: float  # higher = more motion (ok to a point)

    # Flags
    too_short: bool
    too_low_res: bool
    too_dark: bool
    too_bright: bool
    too_blurry: bool
    too_shaky: bool

    hints: List[str]


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _laplacian_var(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _percentile(arr: List[float], p: float) -> float:
    if not arr:
        return 0.0
    return float(np.percentile(np.array(arr, dtype=np.float32), p))


def _compute_shake_and_motion(cap: cv2.VideoCapture, sample_stride: int = 5, max_samples: int = 120) -> Tuple[float, float]:
    """
    Shake: frame-to-frame dominant motion magnitude.
    Motion: overall motion magnitude (useful for coverage).
    """
    # reset to start
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    prev_gray = None
    shake_vals: List[float] = []
    motion_vals: List[float] = []

    samples = 0
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_stride != 0:
            frame_idx += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if prev_gray is not None:
            # Optical flow based on corners
            prev_pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200, qualityLevel=0.01, minDistance=7)
            if prev_pts is not None:
                next_pts, status, _err = cv2.calcOpticalFlowPyrLK(prev_gray, gray, prev_pts, None)
                if next_pts is not None and status is not None:
                    good_prev = prev_pts[status.flatten() == 1]
                    good_next = next_pts[status.flatten() == 1]
                    if len(good_prev) >= 10:
                        diff = good_next - good_prev
                        # dominant motion (median)
                        dx = float(np.median(diff[:, 0]))
                        dy = float(np.median(diff[:, 1]))
                        dom = math.sqrt(dx * dx + dy * dy)

                        # overall motion magnitude (median of magnitudes)
                        mags = np.sqrt((diff[:, 0] ** 2) + (diff[:, 1] ** 2))
                        med_mag = float(np.median(mags))

                        shake_vals.append(dom)
                        motion_vals.append(med_mag)

        prev_gray = gray
        samples += 1
        frame_idx += 1
        if samples >= max_samples:
            break

    if not shake_vals:
        return 0.0, 0.0

    # Normalize a bit by frame size to be resolution independent
    # Use approx diag scale (but keep simple)
    shake = float(np.mean(shake_vals))
    motion = float(np.mean(motion_vals))
    return shake, motion


def analyze_video_quality(
    video_path: str,
    min_duration_sec: float = 10.0,
    min_width: int = 720,
    min_height: int = 720,
    sample_stride: int = 7,
    max_samples: int = 140,
) -> Dict[str, Any]:
    """
    Produces quality metrics + actionable hints.
    Designed to be stable on Render (opencv-python-headless).
    """
    if not os.path.exists(video_path):
        return asdict(VideoQualityResult(
            ok=False,
            message="Video bulunamadı.",
            duration_sec=0.0,
            fps=0.0,
            width=0,
            height=0,
            frame_count=0,
            blur_score_mean=0.0,
            blur_score_p10=0.0,
            exposure_mean=0.0,
            exposure_p10=0.0,
            exposure_p90=0.0,
            shake_score=0.0,
            motion_score=0.0,
            too_short=True,
            too_low_res=True,
            too_dark=False,
            too_bright=False,
            too_blurry=False,
            too_shaky=False,
            hints=["Video dosyası eksik ya da yol hatalı."],
        ))

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return asdict(VideoQualityResult(
            ok=False,
            message="Video açılamadı (codec/format sorunu olabilir).",
            duration_sec=0.0, fps=0.0, width=0, height=0, frame_count=0,
            blur_score_mean=0.0, blur_score_p10=0.0,
            exposure_mean=0.0, exposure_p10=0.0, exposure_p90=0.0,
            shake_score=0.0, motion_score=0.0,
            too_short=True, too_low_res=True,
            too_dark=False, too_bright=False, too_blurry=False, too_shaky=False,
            hints=["Videoyu farklı bir cihazla / tarayıcıyla tekrar çekmeyi deneyin."],
        ))

    fps = _safe_float(cap.get(cv2.CAP_PROP_FPS), 0.0)
    frame_count = int(_safe_float(cap.get(cv2.CAP_PROP_FRAME_COUNT), 0))
    width = int(_safe_float(cap.get(cv2.CAP_PROP_FRAME_WIDTH), 0))
    height = int(_safe_float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT), 0))
    duration = (frame_count / fps) if (fps and frame_count) else 0.0

    blur_scores: List[float] = []
    exposures: List[float] = []

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    idx = 0
    samples = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % sample_stride != 0:
            idx += 1
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur_scores.append(_laplacian_var(gray))
        exposures.append(float(np.mean(gray)))

        samples += 1
        idx += 1
        if samples >= max_samples:
            break

    # Shake + motion
    shake_score, motion_score = _compute_shake_and_motion(cap, sample_stride=sample_stride, max_samples=max_samples)

    cap.release()

    blur_mean = float(np.mean(blur_scores)) if blur_scores else 0.0
    blur_p10 = _percentile(blur_scores, 10)

    exp_mean = float(np.mean(exposures)) if exposures else 0.0
    exp_p10 = _percentile(exposures, 10)
    exp_p90 = _percentile(exposures, 90)

    too_short = duration < min_duration_sec
    too_low_res = (width < min_width) or (height < min_height)

    # exposure heuristics (0-255 grayscale)
    too_dark = exp_mean < 60 or exp_p90 < 90
    too_bright = exp_mean > 200 or exp_p10 > 160

    # blur heuristic: laplacian variance thresholds depend on resolution; keep conservative
    too_blurry = blur_mean < 80 or blur_p10 < 40

    # shake heuristic: in pixel units per sampled frame
    too_shaky = shake_score > 8.0

    hints: List[str] = []
    if too_short:
        hints.append(f"Video çok kısa. En az {int(min_duration_sec)} sn önerilir.")
    if too_low_res:
        hints.append("Çözünürlük düşük. Daha yakından ve net çekin (mümkünse 1080p).")
    if too_dark:
        hints.append("Görüntü karanlık. Daha aydınlık ortamda veya flaş/ışıkla çekin.")
    if too_bright:
        hints.append("Görüntü aşırı parlak. Gölge/karşı ışıkta çekmeyin, pozlamayı düşürün.")
    if too_blurry:
        hints.append("Görüntü bulanık. Lensi temizleyin, 1–2 sn sabitleyip sonra yavaş hareket edin.")
    if too_shaky:
        hints.append("Kamera çok sallanıyor. İki elle tutun, yavaş ve sabit hareket edin.")

    ok = not (too_short or too_low_res or (too_dark and too_bright) or too_blurry)

    msg = "Video kalitesi yeterli." if ok else "Video kalitesi analiz doğruluğunu düşürebilir."
    return asdict(VideoQualityResult(
        ok=ok,
        message=msg,
        duration_sec=float(duration),
        fps=float(fps),
        width=width,
        height=height,
        frame_count=frame_count,
        blur_score_mean=blur_mean,
        blur_score_p10=blur_p10,
        exposure_mean=exp_mean,
        exposure_p10=exp_p10,
        exposure_p90=exp_p90,
        shake_score=float(shake_score),
        motion_score=float(motion_score),
        too_short=too_short,
        too_low_res=too_low_res,
        too_dark=too_dark,
        too_bright=too_bright,
        too_blurry=too_blurry,
        too_shaky=too_shaky,
        hints=hints,
    ))
