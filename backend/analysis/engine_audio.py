# backend/analysis/engine_audio.py
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Dict, Any, Tuple, List

import numpy as np


def _ffmpeg_available() -> bool:
    try:
        p = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
        )
        return p.returncode == 0
    except Exception:
        return False


def _ffmpeg_extract_wav(video_path: str, wav_path: str, sr: int = 16000) -> bool:
    if not _ffmpeg_available():
        return False

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", str(sr),
        "-f", "wav",
        wav_path,
    ]
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        return (
            p.returncode == 0
            and os.path.exists(wav_path)
            and os.path.getsize(wav_path) > 1000
        )
    except Exception:
        return False


def _read_wav_pcm16(wav_path: str) -> Tuple[np.ndarray, int]:
    import wave

    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        fr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    data = np.frombuffer(raw, dtype=np.int16)
    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

    x = data.astype(np.float32) / 32768.0
    return x, fr


def _band_energy(x: np.ndarray, sr: int, f1: float, f2: float) -> float:
    if len(x) < sr:
        return 0.0

    w = np.hanning(len(x)).astype(np.float32)
    X = np.fft.rfft(x * w)
    freqs = np.fft.rfftfreq(len(x), d=1.0 / sr)
    mag2 = np.abs(X) ** 2

    mask = (freqs >= f1) & (freqs <= f2)
    return float(np.sum(mag2[mask]) / (np.sum(mag2) + 1e-9))


def analyze_engine_audio(
    video_path: str,
    *,
    vehicle_is_electric: bool = False,
) -> Dict[str, Any]:
    """
    Production-safe engine audio analysis.
    Never blocks pipeline.
    """

    if vehicle_is_electric:
        return {
            "ok": True,
            "skipped": True,
            "risk_level": "none",
            "signals": {},
            "hints": ["Elektrikli araç – motor sesi analizi uygulanmadı."],
        }

    if not os.path.exists(video_path):
        return {
            "ok": True,
            "skipped": True,
            "risk_level": "unknown",
            "signals": {},
            "hints": ["Motor sesi dosyası bulunamadı."],
        }

    with tempfile.TemporaryDirectory() as td:
        wav_path = os.path.join(td, "engine.wav")

        if not _ffmpeg_extract_wav(video_path, wav_path):
            return {
                "ok": True,
                "skipped": True,
                "risk_level": "unknown",
                "signals": {},
                "hints": [
                    "Motor sesi analizi yapılamadı (ortam kısıtı veya ses yok)."
                ],
            }

        x, sr = _read_wav_pcm16(wav_path)

        if len(x) < sr * 3:
            return {
                "ok": True,
                "skipped": True,
                "risk_level": "unknown",
                "signals": {"duration_sec": float(len(x) / sr)},
                "hints": [
                    "Motor sesi çok kısa; analiz güvenilir değil."
                ],
            }

        roughness = float(np.mean(np.abs(np.diff(x))))
        high = _band_energy(x, sr, 1200, 5000)

        risk_score = 0.0
        risk_score += np.clip((high - 0.20) / 0.25, 0.0, 1.0) * 0.5
        risk_score += np.clip((roughness - 0.025) / 0.025, 0.0, 1.0) * 0.5
        risk_score = float(np.clip(risk_score, 0.0, 1.0))

        risk_level = "low"
        if risk_score >= 0.65:
            risk_level = "high"
        elif risk_score >= 0.40:
            risk_level = "medium"

        hints: List[str] = []
        if high > 0.35:
            hints.append("Yüksek frekanslı sesler tespit edildi.")
        if roughness > 0.04:
            hints.append("Motor sesi düzensiz algılandı.")

        return {
            "ok": True,
            "skipped": False,
            "risk_level": risk_level,
            "signals": {
                "risk_score": risk_score,
                "roughness": roughness,
                "band_high": high,
            },
            "hints": hints,
        }
