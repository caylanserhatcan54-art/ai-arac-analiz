from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Dict, Any, Tuple, List, Optional

import numpy as np


def _ffmpeg_to_wav(input_path: str, wav_path: str, sr: int = 16000) -> bool:
    """
    Convert any audio/video file to mono wav using ffmpeg if available.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
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
    import wave

    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        fr = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)

    data = np.frombuffer(raw, dtype=np.int16 if sampwidth == 2 else np.int16)
    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

    x = data.astype(np.float32) / 32768.0
    return x, int(fr)


def _band_energy(x: np.ndarray, sr: int, f1: float, f2: float) -> float:
    n = len(x)
    if n < sr // 2:
        return 0.0

    w = np.hanning(n).astype(np.float32)
    X = np.fft.rfft(x * w)
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    mag2 = (np.abs(X) ** 2).astype(np.float64)

    mask = (freqs >= f1) & (freqs <= f2)
    band = float(np.sum(mag2[mask]))
    total = float(np.sum(mag2) + 1e-9)
    return band / total


def analyze_engine_audio_file(
    *,
    audio_path: str,
    vehicle_is_electric: bool = False,
    max_duration_sec: float = 12.0,
) -> Dict[str, Any]:
    """
    Engine audio risk analysis for an uploaded audio file.
    - If EV: skip
    - If WAV: read directly
    - Else: try ffmpeg convert; if not available -> skip gracefully

    This is NOT diagnosis.
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

    if not os.path.exists(audio_path):
        return {"ok": False, "skipped": False, "message": "Ses dosyası bulunamadı.", "risk_level": "unknown", "signals": {}, "hints": []}

    with tempfile.TemporaryDirectory() as td:
        wav_path = os.path.join(td, "engine.wav")

        is_wav = audio_path.lower().endswith(".wav")
        if is_wav:
            # copy
            try:
                with open(audio_path, "rb") as src, open(wav_path, "wb") as dst:
                    dst.write(src.read())
                extracted = True
            except Exception:
                extracted = False
        else:
            extracted = _ffmpeg_to_wav(audio_path, wav_path, sr=16000)

        if not extracted:
            return {
                "ok": True,
                "skipped": True,
                "message": "Ses formatı WAV değil ve ffmpeg bulunamadı; ses analizi atlandı.",
                "risk_level": "unknown",
                "signals": {},
                "hints": ["En stabil kullanım için motor sesini WAV formatında yükleyin (10 sn)."],
            }

        x, sr = _read_wav_pcm16(wav_path)

        # limit duration
        max_n = int(sr * max_duration_sec)
        if len(x) > max_n:
            x = x[:max_n]

        if len(x) < sr * 3:
            return {
                "ok": True,
                "skipped": False,
                "message": "Ses çok kısa; risk analizi sınırlı.",
                "risk_level": "unknown",
                "signals": {"duration_sec": float(len(x) / sr)},
                "hints": ["Motor kaputu açıkken 8–12 sn sabit kayıt alın."],
            }

        rms = float(np.sqrt(np.mean(x ** 2)))
        peak = float(np.max(np.abs(x)))
        clipping_ratio = float(np.mean(np.abs(x) > 0.98))
        roughness = float(np.mean(np.abs(np.diff(x))))

        low = _band_energy(x, sr, 40, 250)
        mid = _band_energy(x, sr, 250, 1200)
        high = _band_energy(x, sr, 1200, 5000)

        risk_score = 0.0
        risk_score += np.clip((high - 0.18) / 0.20, 0.0, 1.0) * 0.45
        risk_score += np.clip((roughness - 0.020) / 0.020, 0.0, 1.0) * 0.35
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
            hints.append("Yüksek frekans enerjisi yüksek; kayış/rezonans gibi sesler olabilir (kesin teşhis değildir).")
        if roughness > 0.035:
            hints.append("Ses düzensiz/sert görünüyor; rölantide 8–12 sn sabit kayıt önerilir.")

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
