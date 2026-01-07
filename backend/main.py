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

load_dotenv()

app = FastAPI(title="CARVIX – Photo + Audio Vehicle Pre-Analysis")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prod'da domain ile sınırla
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# JOB QUEUE (Render side)
# =========================================================

def load_jobs():
    if not os.path.exists(JOBS_FILE):
        return []
    with open(JOBS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_jobs(jobs):
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

# =========================================================
# ANALYSIS IMPORTS (LAZY)
# Render'da ağır modüller yoksa bile app açılabilsin diye
# =========================================================
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

# =========================================================
# PATHS
# =========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
AUDIO_DIR = os.path.join(UPLOAD_DIR, "audio")
RESULTS_DIR = os.path.join(UPLOAD_DIR, "results")

JOBS_FILE = os.path.join(BASE_DIR, "jobs_queue.json")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Static serve: /media/...
app.mount("/media", StaticFiles(directory=UPLOAD_DIR), name="media")

# =========================================================
# SIMPLE STORE (disk based)
# =========================================================
def _token_dir(token: str) -> str:
    return os.path.join(IMAGES_DIR, token)

def _audio_path(token: str) -> str:
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
    for ext in [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".webm"]:
        if name.endswith(ext):
            return ext
    return ".bin"

def _next_image_index(out_dir: str) -> int:
    try:
        mx = 0
        for fn in os.listdir(out_dir):
            fn_low = fn.lower()
            if fn_low.startswith("img_"):
                # img_12.jpg -> 12
                part = fn_low.split("_", 1)[1]
                num_part = part.split(".", 1)[0]
                if num_part.isdigit():
                    mx = max(mx, int(num_part))
        return mx + 1
    except Exception:
        return 1

def _public_base_url() -> str:
    """
    Worker'ın indirebilmesi için /media linklerini tam URL'e çeviriyoruz.
    Render'da ENV set et:
      PUBLIC_BASE_URL=https://ai-arac-analiz-backend.onrender.com
    """
    base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    return base

def _ensure_safe_completed(meta: Dict[str, Any], error: Optional[str] = None) -> Dict[str, Any]:
    """
    Frontend'in patlamaması için analysis_completed dönen her kayıtta
    confidence + ai_commentary alanlarını garanti eder.
    """
    out = dict(meta)
    out["status"] = "analysis_completed"
    out["completed_at"] = datetime.utcnow().isoformat()
    out["error"] = error

    if "confidence" not in out or out["confidence"] is None:
        out["confidence"] = {"confidence_score": 0, "confidence_level": "bilinmiyor"}
    if "ai_commentary" not in out or out["ai_commentary"] is None:
        out["ai_commentary"] = {"text": "Yapay zekâ yorumu hazırlanamadı."}
    if "suspicious_images" not in out or out["suspicious_images"] is None:
        out["suspicious_images"] = []

    return out

# =========================================================
# MODELS
# =========================================================
class StartPayload(BaseModel):
    vehicle_type: str = "car"
    scenario: str = "buy_sell"

# =========================================================
# ROOT / HEALTH
# =========================================================
@app.get("/")
def root():
    return {"status": "ok", "mode": "photo_audio"}

@app.get("/health")
def health():
    return {"ok": True}

# =========================================================
# 1) START ANALYSIS (create token)
# =========================================================
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
        "job_id": None,  # worker queue için
    }
    _save_result(token, meta)
    return {"ok": True, "token": token}

# =========================================================
# 2) UPLOAD IMAGES
# =========================================================
@app.post("/analysis/{token}/images")
async def upload_images(token: str, images: List[UploadFile] = File(...)):
    data = _load_result(token)
    if not data:
        raise HTTPException(404, "Session not found")

    out_dir = _token_dir(token)
    os.makedirs(out_dir, exist_ok=True)

    start_idx = _next_image_index(out_dir)

    saved_disk_paths: List[str] = []
    max_images = 30

    existing = len(data.get("images") or [])
    remaining = max(0, max_images - existing)
    if remaining <= 0:
        raise HTTPException(400, "Maksimum 30 fotoğraf sınırına ulaşıldı.")

    for img in images[:remaining]:
        content = await img.read()
        if not content or len(content) < 2000:
            continue

        name = (img.filename or "img.jpg").lower()
        ext = ".jpg"
        if name.endswith(".png"):
            ext = ".png"
        elif name.endswith(".webp"):
            ext = ".webp"
        elif name.endswith(".jpeg") or name.endswith(".jpg"):
            ext = ".jpg"

        fn = f"img_{start_idx + len(saved_disk_paths)}{ext}"
        path = os.path.join(out_dir, fn)

        with open(path, "wb") as f:
            f.write(content)

        saved_disk_paths.append(path)

    if not saved_disk_paths:
        raise HTTPException(400, "No valid images uploaded")

    rels = [f"/media/images/{token}/{os.path.basename(p)}" for p in saved_disk_paths]
    data["images"] = (data.get("images") or []) + rels
    data["status"] = "images_uploaded"
    data["error"] = None
    _save_result(token, data)

    return {"ok": True, "uploaded": len(saved_disk_paths), "images": rels}

# =========================================================
# 3) UPLOAD ENGINE AUDIO (optional)
# =========================================================
@app.post("/analysis/{token}/audio")
async def upload_audio(token: str, audio: UploadFile = File(...)):
    data = _load_result(token)
    if not data:
        raise HTTPException(404, "Session not found")

    content = await audio.read()
    if not content or len(content) < 2000:
        raise HTTPException(400, "Audio too small")

    ext = _safe_ext_from_filename(audio.filename or "")
    ap = os.path.join(AUDIO_DIR, f"{token}{ext}")

    with open(ap, "wb") as f:
        f.write(content)

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

    lp = _audio_path(token)
    if os.path.exists(lp):
        return lp
    return None

# =========================================================
# 4) RUN ANALYSIS
# - USE_GPU_WORKER=1 => queue job (Vast worker çözer)
# - else => local analysis (opsiyonel)
# =========================================================
@app.post("/analysis/{token}/run")
def run_analysis(token: str):
    meta = _load_result(token)
    if not meta:
        raise HTTPException(404, "Session not found")

    images_rel = meta.get("images") or []
    if len(images_rel) < 3:
        raise HTTPException(400, f"En az 3 fotoğraf yükleyin. (şu an: {len(images_rel)})")

    # /media/... -> disk path (local)
    image_paths: List[str] = []
    for rel in images_rel:
        if not isinstance(rel, str) or not rel.startswith("/media/"):
            continue
        disk = os.path.join(UPLOAD_DIR, rel.replace("/media/", "").lstrip("/"))
        if os.path.exists(disk):
            image_paths.append(disk)

    if not image_paths:
        raise HTTPException(400, "Images not found on server")

    vehicle_type = meta.get("vehicle_type") or "car"
    scenario = meta.get("scenario") or "buy_sell"

    # --------------------------
    # MODE A: GPU WORKER QUEUE
    # --------------------------
    if (os.getenv("USE_GPU_WORKER") or "").strip() == "1":
        base = _public_base_url()
        if not base:
            # Bu yoksa worker linkleri indiremez
            failed = _ensure_safe_completed(meta, error="PUBLIC_BASE_URL env eksik (worker indirme linki oluşturulamıyor)")
            _save_result(token, failed)
            return {"ok": False, "error": failed["error"]}

        # worker indirebilsin diye full URL yap
        image_urls = [base + rel for rel in images_rel]

        job_id = token  # token ile aynı tutuyoruz
        job = {
            "job_id": job_id,
            "images": image_urls,
            "meta": {
                "token": token,
                "vehicle_type": vehicle_type,
                "scenario": scenario,
                # audio full url (varsa)
                "audio": (base + meta["audio"]) if meta.get("audio") else None,
            },
            "created_at": datetime.utcnow().isoformat(),
            "status": "queued",
        }

        JOBS.append(job)

        meta["status"] = "queued"
        meta["job_id"] = job_id
        meta["error"] = None
        _save_result(token, meta)

        return {"ok": True, "queued": True, "job_id": job_id}

    # --------------------------
    # MODE B: LOCAL ANALYSIS
    # --------------------------
    meta["status"] = "processing"
    meta["error"] = None
    _save_result(token, meta)

    try:
        (
            run_damage_pipeline,
            analyze_engine_audio_file,
            compute_confidence,
            generate_human_commentary,
            extract_suspicious_frames_from_images,
        ) = _lazy_import_analysis()

        damage = run_damage_pipeline(
            image_paths,
            vehicle_type=vehicle_type,
            yolo_model_path=os.getenv("YOLO_MODEL_PATH") or None,
            yolo_conf=float(os.getenv("YOLO_CONF") or 0.25),
            yolo_iou=float(os.getenv("YOLO_IOU") or 0.45),
            max_frames_to_process=28,
        )

        suspicious_dir = os.path.join(_token_dir(token), "suspicious")
        suspicious_images = extract_suspicious_frames_from_images(
            token=token,
            damage=damage,
            output_dir=suspicious_dir,
            max_images=4,
        )

        for item in suspicious_images:
            p = item.get("image_path")
            if p and isinstance(p, str) and os.path.exists(p):
                relp = p.replace(UPLOAD_DIR, "").replace("\\", "/")
                if not relp.startswith("/"):
                    relp = "/" + relp
                item["image_path"] = "/media" + relp

        engine_audio = None
        ap = _find_audio_file(token)
        if ap and os.path.exists(ap):
            engine_audio = analyze_engine_audio_file(
                audio_path=ap,
                vehicle_is_electric=(vehicle_type == "electric_car"),
                max_duration_sec=12.0,
            )

        video_quality = {"ok": True, "hints": []}
        coverage = {"coverage_ratio": min(1.0, len(image_paths) / 12.0), "hints": []}
        if len(image_paths) < 6:
            coverage["hints"].append("Fotoğraf sayısı az; daha fazla açı eklerseniz analiz güveni artar.")

        confidence = compute_confidence(
            video_quality=video_quality,
            coverage=coverage,
            damage=damage,
            engine_audio=engine_audio,
        )

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
        err = str(e)
        failed = _ensure_safe_completed(meta, error=err)
        _save_result(token, failed)
        return {"ok": False, "error": err}

# =========================================================
# 5) GET RESULT
# (worker sonucu geldiyse token json'da olacak)
# =========================================================
@app.get("/analysis/{token}")
def get_analysis(token: str):
    data = _load_result(token)
    if not data:
        raise HTTPException(404, "Not found")

    # 🔥 WORKER SONUCU VAR MI?
    worker_result = RESULTS.get(token)
    if worker_result:
        data["yolo"] = worker_result.get("result")

    return data

# =========================================================
# JOB QUEUE ENDPOINTS
# Worker burada job çeker / sonucu bırakır
# =========================================================
@app.post("/jobs/create")
def jobs_create(payload: Dict[str, Any]):
    job_id = payload.get("job_id")
    images = payload.get("images")
    meta = payload.get("meta") or {}

    if not job_id or not isinstance(images, list) or len(images) == 0:
        raise HTTPException(400, "job_id ve images(list) gerekli")

    jobs = load_jobs()

    jobs.append({
        "job_id": job_id,
        "images": images,
        "meta": meta,
        "created_at": datetime.utcnow().isoformat(),
        "status": "queued",
    })

    save_jobs(jobs)
    return {"ok": True, "job_id": job_id}

@app.get("/jobs/next")
def jobs_next():
    jobs = load_jobs()

    if not jobs:
        return {"job": None}

    job = jobs.pop(0)
    job["status"] = "processing"
    job["started_at"] = datetime.utcnow().isoformat()

    save_jobs(jobs)
    return {"job": job}

@app.post("/jobs/{job_id}/result")
def jobs_result(job_id: str, payload: Dict[str, Any]):
    """
    Worker sonucu buraya bırakır.
    - RESULTS dict'e yaz
    - Ayrıca /analysis/{token} endpoint'i çalışsın diye token dosyasını da güncelle
    """
    RESULTS[job_id] = {
        "status": "done",
        "job_id": job_id,
        "result": payload,
        "completed_at": datetime.utcnow().isoformat(),
    }

    # job_id == token varsayımı (biz token ile aynı kullanıyoruz)
    token = job_id
    meta = _load_result(token) or {"token": token, "created_at": datetime.utcnow().isoformat()}

    # Worker payload'unu CARVIX report formatına normalize et
    # (frontend crash olmasın diye field'leri garanti ediyoruz)
    result = {
        "token": token,
        "vehicle_type": (meta.get("vehicle_type") or payload.get("vehicle_type") or "car"),
        "scenario": (meta.get("scenario") or payload.get("scenario") or "buy_sell"),
        "status": "analysis_completed",
        "created_at": meta.get("created_at"),
        "completed_at": datetime.utcnow().isoformat(),
        "images": meta.get("images", []),
        "suspicious_images": payload.get("suspicious_images") or [],
        "damage": payload.get("damage"),
        "engine_audio": payload.get("engine_audio"),
        "confidence": payload.get("confidence") or {"confidence_score": 0, "confidence_level": "bilinmiyor"},
        "ai_commentary": payload.get("ai_commentary") or {"text": "Yapay zekâ yorumu hazırlanamadı."},
        "error": payload.get("error"),
        "job_id": meta.get("job_id") or job_id,
    }

    # GARANTİ
    result = _ensure_safe_completed(result, error=result.get("error"))

    _save_result(token, result)

    return {"ok": True}

@app.get("/jobs/{job_id}")
def jobs_get(job_id: str):
    if job_id not in RESULTS:
        return {"status": "processing", "job_id": job_id}
    return RESULTS[job_id]
