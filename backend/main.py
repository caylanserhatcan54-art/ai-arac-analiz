from __future__ import annotations

import os
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import UploadFile, File, HTTPException
from typing import List

# =========================
# ANALYSIS IMPORTS
# =========================
def _lazy_import_analysis():
    from analysis.damage_pipeline import run_damage_pipeline
    from analysis.engine_audio import analyze_engine_audio_file
    from analysis.ai_confidence import compute_confidence
    from analysis.ai_commentary import generate_human_commentary
    from analysis.suspicious_frames import extract_suspicious_frames_from_images
    return (
        run_damage_pipeline,
        analyze_engine_audio_file,
        compute_confidence,
        generate_human_commentary,
        extract_suspicious_frames_from_images,
    )

load_dotenv()

app = FastAPI(title="CARVIX – Photo + Audio Vehicle Pre-Analysis")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prod'da domain ile sınırla
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
AUDIO_DIR = os.path.join(UPLOAD_DIR, "audio")
RESULTS_DIR = os.path.join(UPLOAD_DIR, "results")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Static serve: /media/...
app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="media")

# =========================
# SIMPLE STORE (disk based)
# =========================
def _token_dir(token: str) -> str:
    return os.path.join(IMAGES_DIR, token)

def _audio_path(token: str) -> str:
    # Geriye dönük uyumluluk için default bin; ama artık orijinal uzantı ile kaydediyoruz
    return os.path.join(AUDIO_DIR, f"{token}.bin")

def _audio_meta_path(token: str) -> str:
    return os.path.join(AUDIO_DIR, f"{token}.meta.json")

def _result_path(token: str) -> str:
    return os.path.join(RESULTS_DIR, f"{token}.json")

def _load_result(token: str) -> Optional[Dict[str, Any]]:
    rp = _result_path(token)
    if not os.path.exists(rp):
        return None
    with open(rp, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_result(token: str, data: Dict[str, Any]) -> None:
    rp = _result_path(token)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _safe_ext_from_filename(name: str) -> str:
    name = (name or "").lower().strip()
    # izinli uzantılar
    for ext in [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".webm"]:
        if name.endswith(ext):
            return ext
    return ".bin"

def _next_image_index(out_dir: str) -> int:
    """
    Aynı token'a tekrar upload edilince img_1.jpg overwrite olmasın diye
    klasördeki mevcut img_*.ext dosyalarından index bulur.
    """
    try:
        mx = 0
        for fn in os.listdir(out_dir):
            fn_low = fn.lower()
            if fn_low.startswith("img_"):
                # img_12.jpg -> 12
                parts = fn_low.split("_", 1)
                if len(parts) != 2:
                    continue
                num_part = parts[1].split(".", 1)[0]
                if num_part.isdigit():
                    mx = max(mx, int(num_part))
        return mx + 1
    except Exception:
        return 1

# =========================
# MODELS
# =========================
class StartPayload(BaseModel):
    vehicle_type: str = "car"
    scenario: str = "buy_sell"  # artık tek yerde toplu

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {"status": "ok", "mode": "photo_audio"}

# =========================
# 1) START ANALYSIS (create token)
# =========================
@app.post("/analysis/start")
def analysis_start(payload: StartPayload):
    token = str(uuid.uuid4())
    os.makedirs(_token_dir(token), exist_ok=True)

    meta = {
        "token": token,
        "vehicle_type": payload.vehicle_type,
        "scenario": payload.scenario,
        "status": "started",
        "created_at": datetime.utcnow().isoformat(),
        "images": [],
        "audio": None,
        "error": None,
    }
    _save_result(token, meta)
    return {"ok": True, "token": token}

# =========================
# 2) UPLOAD IMAGES (gallery images)
# =========================
@app.post("/analysis/{token}/images")
async def upload_images(token: str, images: List[UploadFile] = File(...)):
    data = _load_result(token)
    if not data:
        raise HTTPException(404, "Session not found")

    out_dir = _token_dir(token)
    os.makedirs(out_dir, exist_ok=True)

    # ✅ overwrite olmasın diye başlangıç index'i folder'dan hesapla
    start_idx = _next_image_index(out_dir)

    saved_disk_paths: List[str] = []
    max_images = 30

    # mevcut toplamı da hesaba kat (30 limiti)
    existing = len(data.get("images") or [])
    remaining = max(0, max_images - existing)
    if remaining <= 0:
        raise HTTPException(400, "Maksimum 30 fotoğraf sınırına ulaşıldı.")

    for i, img in enumerate(images[:remaining]):
        content = await img.read()
        if not content or len(content) < 2000:
            continue

        # ext normalize (foto için)
        name = (img.filename or f"img_{i+1}.jpg").lower()
        ext = ".jpg"
        if name.endswith(".png"):
            ext = ".png"
        elif name.endswith(".jpeg") or name.endswith(".jpg"):
            ext = ".jpg"
        elif name.endswith(".webp"):
            ext = ".webp"

        fn = f"img_{start_idx + len(saved_disk_paths)}{ext}"
        path = os.path.join(out_dir, fn)

        with open(path, "wb") as f:
            f.write(content)

        saved_disk_paths.append(path)

    if not saved_disk_paths:
        raise HTTPException(400, "No valid images uploaded")

    # update meta (store as relative media url for frontend)
    rels = [f"/media/images/{token}/{os.path.basename(p)}" for p in saved_disk_paths]
    data["images"] = (data.get("images") or []) + rels
    data["status"] = "images_uploaded"
    data["error"] = None
    _save_result(token, data)

    return {"ok": True, "uploaded": len(saved_disk_paths), "images": rels}

# =========================
# 3) UPLOAD ENGINE AUDIO (optional)
#    Accept any file; if ffmpeg missing and format not wav -> will skip gracefully
# =========================
@app.post("/analysis/{token}/audio")
async def upload_audio(token: str, audio: UploadFile = File(...)):
    data = _load_result(token)
    if not data:
        raise HTTPException(404, "Session not found")

    content = await audio.read()
    if not content or len(content) < 2000:
        raise HTTPException(400, "Audio too small")

    # ✅ .bin yerine mümkünse orijinal uzantı
    ext = _safe_ext_from_filename(audio.filename or "")
    ap = os.path.join(AUDIO_DIR, f"{token}{ext}")

    with open(ap, "wb") as f:
        f.write(content)

    # meta yaz (analizde doğru dosyayı bulmak için)
    meta = {
        "filename": audio.filename,
        "content_type": audio.content_type,
        "saved_path": ap,
        "saved_at": datetime.utcnow().isoformat(),
    }
    with open(_audio_meta_path(token), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    data["audio"] = f"/media/audio/{os.path.basename(ap)}"
    data["status"] = "audio_uploaded"
    data["error"] = None
    _save_result(token, data)

    return {"ok": True, "audio": data["audio"]}

def _find_audio_file(token: str) -> Optional[str]:
    """
    Token için kaydedilmiş ses dosyasını bulur:
    - önce meta.json'dan
    - yoksa bilinen uzantıları tarar
    - en son legacy .bin
    """
    mp = _audio_meta_path(token)
    if os.path.exists(mp):
        try:
            with open(mp, "r", encoding="utf-8") as f:
                j = json.load(f)
            p = j.get("saved_path")
            if p and os.path.exists(p):
                return p
        except Exception:
            pass

    for ext in [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".webm", ".bin"]:
        p = os.path.join(AUDIO_DIR, f"{token}{ext}")
        if os.path.exists(p):
            return p

    # legacy
    lp = _audio_path(token)
    if os.path.exists(lp):
        return lp
    return None

# =========================
# 4) RUN ANALYSIS (SYNC, NO BACKGROUND)
# =========================
@app.post("/analysis/{token}/run")
def run_analysis(token: str):
    meta = _load_result(token)
    if not meta:
        raise HTTPException(404, "Session not found")

    images_rel = meta.get("images") or []
    if len(images_rel) < 3:
        raise HTTPException(400, "En az 3 fotoğraf yükleyin (ön/arka/yan gibi).")

    # convert /media/... to disk path
    image_paths: List[str] = []
    for rel in images_rel:
        # rel: /media/images/{token}/file.jpg
        if not isinstance(rel, str):
            continue
        if not rel.startswith("/media/"):
            continue
        disk = os.path.join(UPLOAD_DIR, rel.replace("/media/", "").lstrip("/"))
        if os.path.exists(disk):
            image_paths.append(disk)

    if not image_paths:
        raise HTTPException(400, "Images not found on server")

    vehicle_type = meta.get("vehicle_type") or "car"
    scenario = meta.get("scenario") or "buy_sell"

    meta["status"] = "processing"
    meta["error"] = None
    _save_result(token, meta)

    try:
        # -------------------------
        # DAMAGE (photo-based)
        # -------------------------
        damage = run_damage_pipeline(
            image_paths,
            vehicle_type=vehicle_type,
            # YOLO is optional via env
            yolo_model_path=os.getenv("YOLO_MODEL_PATH") or None,
            yolo_conf=float(os.getenv("YOLO_CONF") or 0.25),
            yolo_iou=float(os.getenv("YOLO_IOU") or 0.45),
            max_frames_to_process=28,
        )

        # -------------------------
        # SUSPICIOUS THUMBS (2x2)
        # -------------------------
        suspicious_dir = os.path.join(_token_dir(token), "suspicious")
        suspicious_images = extract_suspicious_frames_from_images(
            token=token,
            damage=damage,
            output_dir=suspicious_dir,
            max_images=4,
        )

        # rewrite suspicious image paths to /media urls
        for item in suspicious_images:
            p = item.get("image_path")
            if p and isinstance(p, str) and os.path.exists(p):
                # .../uploads/images/{token}/suspicious/x.jpg -> /media/images/{token}/suspicious/x.jpg
                relp = p.replace(UPLOAD_DIR, "").replace("\\", "/")
                if not relp.startswith("/"):
                    relp = "/" + relp
                item["image_path"] = "/media" + relp

        # -------------------------
        # ENGINE AUDIO (optional)
        # -------------------------
        engine_audio = None
        ap = _find_audio_file(token)
        if ap and os.path.exists(ap):
            engine_audio = analyze_engine_audio_file(
                audio_path=ap,
                vehicle_is_electric=(vehicle_type == "electric_car"),
                max_duration_sec=12.0,  # 10 sn hedef, biraz tolerans
            )

        # -------------------------
        # CONFIDENCE (no video_quality / coverage now)
        # -------------------------
        # We emulate minimal "video_quality" and "coverage" with photo counts.
        # (keeps your compute_confidence structure intact)
        video_quality = {"ok": True, "hints": []}  # placeholder
        coverage = {
            "coverage_ratio": min(1.0, len(image_paths) / 12.0),
            "hints": [],
        }
        if len(image_paths) < 6:
            coverage["hints"].append("Fotoğraf sayısı az; daha fazla açı eklerseniz analiz güveni artar.")

        confidence = compute_confidence(
            video_quality=video_quality,
            coverage=coverage,
            damage=damage,
            engine_audio=engine_audio,
        )

        # -------------------------
        # AI COMMENTARY
        # -------------------------
        ai_commentary = generate_human_commentary(
            vehicle_type=vehicle_type,
            scenario=scenario,
            video_quality=video_quality,
            coverage=coverage,
            damage=damage,
            engine_audio=engine_audio,
            confidence=confidence,
        )

        result = {
            "token": token,
            "vehicle_type": vehicle_type,
            "scenario": scenario,
            "status": "analysis_completed",
            "created_at": meta.get("created_at"),
            "completed_at": datetime.utcnow().isoformat(),
            "images": meta.get("images", []),
            "suspicious_images": suspicious_images,
            "damage": damage,
            "engine_audio": engine_audio,
            "confidence": confidence,
            "ai_commentary": ai_commentary,
            "error": None,
        }

        _save_result(token, result)
        return {"ok": True, "result": result}

    except Exception as e:
        # ✅ Asla processing'de takılma: hata da olsa completed yap ve error yaz
        err = str(e)
        failed = dict(meta)
        failed.update({
            "status": "analysis_completed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": err,
        })
        _save_result(token, failed)
        return {"ok": False, "error": err}

# =========================
# 5) GET RESULT
# =========================
@app.get("/analysis/{token}")
def get_analysis(token: str):
    data = _load_result(token)
    if not data:
        raise HTTPException(404, "Not found")
    return data

# =========================
# JOB QUEUE (Render side)
# =========================
JOBS: List[Dict[str, Any]] = []
RESULTS: Dict[str, Any] = {}


@app.post("/jobs/create")
def jobs_create(payload: Dict[str, Any]):
    job_id = payload.get("job_id")
    images = payload.get("images")  # image URLs list
    meta = payload.get("meta") or {}

    if not job_id or not isinstance(images, list) or len(images) == 0:
        raise HTTPException(400, "job_id ve images(list) gerekli")

    JOBS.append({
        "job_id": job_id,
        "images": images,
        "meta": meta,
        "created_at": datetime.utcnow().isoformat(),
        "status": "queued",
    })
    return {"ok": True, "job_id": job_id}


@app.get("/jobs/next")
def jobs_next():
    if not JOBS:
        return {"job": None}

    job = JOBS.pop(0)
    job["status"] = "processing"
    job["started_at"] = datetime.utcnow().isoformat()
    return {"job": job}


@app.post("/jobs/{job_id}/result")
def jobs_result(job_id: str, payload: Dict[str, Any]):
    RESULTS[job_id] = {
        "status": "done",
        "job_id": job_id,
        "result": payload,
        "completed_at": datetime.utcnow().isoformat(),
    }
    return {"ok": True}


@app.get("/jobs/{job_id}")
def jobs_get(job_id: str):
    if job_id not in RESULTS:
        return {"status": "processing", "job_id": job_id}
    return RESULTS[job_id]