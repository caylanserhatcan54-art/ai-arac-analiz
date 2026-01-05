# backend/analysis/engine_audio.py
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Dict, Any, Optional, Tuple, List

import numpy as np


def _ffmpeg_extract_wav(video_path: str, wav_path: str, sr: int = 16000) -> bool:
    """
    Extract mono wav using ffmpeg if available.
    Returns True if successful.
    """
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
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return p.returncode == 0 and os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000
    except Exception:
        return False


def _read_wav_pcm16(wav_path: str) -> Tuple[np.ndarray, int]:
    """
    Minimal WAV reader (PCM16 mono) using Python stdlib via numpy.
    Avoids extra dependencies.
    """
    import wave

    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        fr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    if sampwidth != 2:
        # fallback: interpret as int16 anyway
        data = np.frombuffer(raw, dtype=np.int16)
    else:
        data = np.frombuffer(raw, dtype=np.int16)

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

    x = data.astype(np.float32) / 32768.0
    return x, int(fr)


def _band_energy(x: np.ndarray, sr: int, f1: float, f2: float) -> float:
    # FFT band energy ratio
    n = len(x)
    if n < sr // 2:
        return 0.0
    # window
    w = np.hanning(n).astype(np.float32)
    X = np.fft.rfft(x * w)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    mag2 = (np.abs(X) ** 2).astype(np.float64)

    mask = (freqs >= f1) & (freqs <= f2)
    band = float(np.sum(mag2[mask]))
    total = float(np.sum(mag2) + 1e-9)
    return band / total


def analyze_engine_audio(
    video_path: str,
    *,
    vehicle_is_electric: bool = False,
) -> Dict[str, Any]:
    """
    Engine audio risk analysis:
    - If EV: skip (return ok with skipped flag)
    - Else: extract audio with ffmpeg, compute simple indicators
      (roughness, high-frequency energy, clipping, noise floor).
    This is NOT a mechanical diagnosis; it's a risk signal.
    """
    if vehicle_is_electric:
        return {
            "ok": True,
            "skipped": True,
            "message": "Elektrikli araç seçildi; motor sesi analizi atlandı.",
            "risk_level": "none",
            "signals": {},
            "hints": [],
        }

    if not os.path.exists(video_path):
        return {"ok": False, "skipped": False, "message": "Video bulunamadı.", "risk_level": "unknown", "signals": {}, "hints": []}

    with tempfile.TemporaryDirectory() as td:
        wav_path = os.path.join(td, "engine.wav")
        extracted = _ffmpeg_extract_wav(video_path, wav_path, sr=16000)

        if not extracted:
            return {
                "ok": False,
                "skipped": False,
                "message": "Ses çıkarılamadı (ffmpeg yok / ses track yok olabilir).",
                "risk_level": "unknown",
                "signals": {},
                "hints": ["Motor sesi analizi için videoda motor sesi net olmalı ve ffmpeg erişilebilir olmalı."],
            }

        x, sr = _read_wav_pcm16(wav_path)
        if len(x) < sr * 3:
            return {
                "ok": True,
                "skipped": False,
                "message": "Ses çok kısa; risk analizi sınırlı.",
                "risk_level": "unknown",
                "signals": {"duration_sec": float(len(x) / sr)},
                "hints": ["Motor kaputu açıkken 5–10 sn sabit çekip sesi net kaydedin."],
            }

        # Signals
        rms = float(np.sqrt(np.mean(x ** 2)))
        peak = float(np.max(np.abs(x)))
        clipping_ratio = float(np.mean(np.abs(x) > 0.98))

        # roughness proxy: mean absolute diff
        roughness = float(np.mean(np.abs(np.diff(x))))

        # band energies
        low = _band_energy(x, sr, 40, 250)       # fundamental-ish
        mid = _band_energy(x, sr, 250, 1200)
        high = _band_energy(x, sr, 1200, 5000)   # whine/metal/air leak-ish

        # Interpret heuristically
        risk_score = 0.0

        # too noisy / too harsh high freq
        risk_score += np.clip((high - 0.18) / 0.20, 0.0, 1.0) * 0.45
        # roughness (irregularity)
        risk_score += np.clip((roughness - 0.020) / 0.020, 0.0, 1.0) * 0.35
        # clipping indicates bad recording (lower confidence)
        risk_score += np.clip((clipping_ratio - 0.01) / 0.05, 0.0, 1.0) * 0.20

        risk_score = float(np.clip(risk_score, 0.0, 1.0))

        risk_level = "low"
        if risk_score >= 0.65:
            risk_level = "high"
        elif risk_score >= 0.40:
            risk_level = "medium"

        hints: List[str] = []
        if clipping_ratio > 0.02:
            hints.append("Ses kaydı patlıyor (clipping). Telefonu biraz uzak tutup tekrar kaydedin.")
        if high > 0.30:
            hints.append("Yüksek frekans enerjisi yüksek; kayış/alternatör/rezonans gibi sesler olabilir (kesin teşhis değildir).")
        if roughness > 0.035:
            hints.append("Ses düzensiz/sert görünüyor; rölantide 5–10 sn sabit kayıt önerilir.")

        return {
            "ok": True,
            "skipped": False,
            "message": "Motor sesi analizi tamam.",
            "risk_level": risk_level,
            "signals": {
                "duration_sec": float(len(x) / sr),
                "rms": rms,
                "peak": peak,
                "clipping_ratio": clipping_ratio,
                "roughness": roughness,
                "band_low": low,
                "band_mid": mid,
                "band_high": high,
                "risk_score": risk_score,
            },
            "hints": hints,
        }
