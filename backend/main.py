from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

import os
import uuid
from typing import Dict

# =========================
# ANALYSIS IMPORTS
# =========================
from analysis.video_quality import analyze_video_quality
from analysis.frame_extractor import extract_frames
from analysis.coverage_check import estimate_coverage
from analysis.damage_pipeline import run_damage_pipeline
from analysis.engine_audio import analyze_engine_audio
from analysis.ai_confidence import compute_confidence
from analysis.ai_commentary import generate_human_commentary
from analysis.suspicious_frames import extract_suspicious_frames

# =========================
# ENV
# =========================
load_dotenv()

# =========================
# APP
# =========================
app = FastAPI(title="CARVIX – AI Araç Ön Analiz")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prod'da domain'e daraltırsın
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
FRAMES_DIR = os.path.join(BASE_DIR, "analysis_frames")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

# ✅ Şüpheli görselleri webden göstermek için static mount
# URL:  /media/<token>/suspicious/suspicious_1.jpg
app.mount("/media", StaticFiles(directory=FRAMES_DIR), name="media")

# =========================
# IN-MEMORY SESSION (MVP)
# =========================
SESSIONS: Dict[str, dict] = {}

# =========================
# MODELS
# =========================
class SessionUpdate(BaseModel):
    scenario: str
    vehicle_type: str

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"status": "ok"}

# =========================
# PAYMENT (MOCK)
# =========================
@app.post("/payment/start")
def start_payment():
    token = str(uuid.uuid4())

    SESSIONS[token] = {
        "token": token,
        "scenario": None,
        "vehicle_type": None,
        "status": "paid",
        "video_path": None,
        "error": None,
    }

    return {"paid": True, "token": token}

# =========================
# SESSION
# =========================
@app.get("/session/{token}")
def get_session(token: str):
    if token not in SESSIONS:
        raise HTTPException(404, "Session not found")
    return SESSIONS[token]

@app.post("/session/{token}/update")
def update_session(token: str, payload: SessionUpdate):
    if token not in SESSIONS:
        raise HTTPException(404, "Session not found")

    SESSIONS[token].update({
        "scenario": payload.scenario,
        "vehicle_type": payload.vehicle_type,
        "status": "configured",
    })

    return {"ok": True}

# =========================
# 🔥 FULL ANALYSIS (SYNC)
# =========================
def run_full_analysis(token: str):
    session = SESSIONS[token]
    video_path = session["video_path"]

    session["status"] = "processing"
    session["error"] = None

    try:
        # 1) Video kalite
        video_quality = analyze_video_quality(video_path)

        # 2) Frame extraction
        frame_out = os.path.join(FRAMES_DIR, token)
        frames_result = extract_frames(video_path, frame_out)

        # 3) Coverage
        coverage = estimate_coverage(frames_result["frames"])

        # 4) Damage
        damage = run_damage_pipeline(
            frames_result["frames"],
            vehicle_type=session.get("vehicle_type", "car"),
        )

        # 5) Engine audio
        engine_audio = analyze_engine_audio(
            video_path,
            vehicle_is_electric=session.get("vehicle_type") == "electric_car",
        )

        # 6) Confidence
        confidence = compute_confidence(
            video_quality=video_quality,
            coverage=coverage,
            damage=damage,
            engine_audio=engine_audio,
        )

        # 7) AI commentary
        ai_commentary = generate_human_commentary(
            vehicle_type=session.get("vehicle_type", "car"),
            scenario=session.get("scenario", ""),
            video_quality=video_quality,
            coverage=coverage,
            damage=damage,
            engine_audio=engine_audio,
            confidence=confidence,
        )

        # 8) Suspicious frames (URL path döner)
        suspicious_dir = os.path.join(frame_out, "suspicious")
        suspicious_images = extract_suspicious_frames(
            token=token,
            damage=damage,
            output_dir=suspicious_dir,
            max_images=4,
        )

        session.update({
            "video_quality": video_quality,
            "coverage": coverage,
            "damage": damage,
            "engine_audio": engine_audio,
            "confidence": confidence,
            "ai_commentary": ai_commentary,
            "suspicious_images": suspicious_images,
        })

    except Exception as e:
        session["error"] = str(e)

    finally:
        # ✅ her koşulda tamamlandı (takılma yok)
        session["status"] = "analysis_completed"

# =========================
# VIDEO UPLOAD (SYNC)
# =========================
@app.post("/upload/{token}/video")
async def upload_video(token: str, video: UploadFile = File(...)):
    if token not in SESSIONS:
        raise HTTPException(404, "Session not found")

    session = SESSIONS[token]

    save_path = os.path.join(UPLOAD_DIR, f"{token}.webm")
    contents = await video.read()

    if len(contents) < 1000:
        raise HTTPException(400, "Video too small")

    with open(save_path, "wb") as f:
        f.write(contents)

    session["video_path"] = save_path

    # 🔥 SENKRON ANALİZ (en sağlam MVP)
    run_full_analysis(token)

    # sonucu direkt döndür
    return {
        "ok": True,
        "status": session.get("status"),
        "error": session.get("error"),
        "confidence": session.get("confidence"),
        "ai_commentary": session.get("ai_commentary"),
        "suspicious_images": session.get("suspicious_images"),
    }
