# backend/main.py
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import os
import uuid
import re
import json

from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


from backend.firebase import db

# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------
# App
# -------------------------------------------------------------------
app = FastAPI(title="Carvix Backend", version="1.0.0")

# -------------------------------------------------------------------
# CORS
# -------------------------------------------------------------------
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://carvix-web.vercel.app,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Static uploads
# -------------------------------------------------------------------
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def utcnow() -> datetime:
    # Firestore için timezone-aware tarih iyi pratik
    return datetime.now(timezone.utc)

def safe_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-zA-Z0-9._-]", "", name)
    return name or "image.png"

def public_base_url() -> str:
    return os.getenv(
        "PUBLIC_BASE_URL",
        "https://ai-arac-analiz-backend.onrender.com"
    )

def parse_views(views_raw: str) -> List[Dict[str, str]]:
    try:
        data = json.loads(views_raw)
        if not isinstance(data, list):
            raise ValueError("views must be a list")
        for v in data:
            if not isinstance(v, dict):
                raise ValueError("views items must be objects")
            if "filename" not in v or "part" not in v:
                raise ValueError("views items must include filename and part")
        return data
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="views must be valid JSON: [{filename, part}, ...]"
        )

# -------------------------------------------------------------------
# Health
# -------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}

# -------------------------------------------------------------------
# Create Job (Upload) -> Firestore analyses + job_queue
# -------------------------------------------------------------------
@app.post("/jobs")
async def create_job(
    token: str = Form(...),
    views: str = Form(...),
    files: List[UploadFile] = File(...)
):
    analysis_id = str(uuid.uuid4())
    views_meta = parse_views(views)

    if len(files) != len(views_meta):
        raise HTTPException(
            status_code=400,
            detail="files count must match views metadata count"
        )

    saved_images = []

    for file, view in zip(files, views_meta):
        original = file.filename or "image.png"
        clean = safe_filename(original)
        new_name = f"{uuid.uuid4()}_{clean}"
        out_path = UPLOAD_DIR / new_name

        content = await file.read()
        out_path.write_bytes(content)

        saved_images.append({
            "filename": new_name,
            "url": f"{public_base_url()}/uploads/{new_name}",
            "part": view["part"],
            "original_name": original,
            "content_type": file.content_type,
        })

    now = utcnow()

    analysis_doc = {
        "id": analysis_id,
        "token": token,
        "status": "queued",             # queued | processing | done | failed
        "created_at": now,
        "expire_at": now + timedelta(hours=24),
        "images": saved_images,
        "result": None,
        "error": None,
    }

    # ✅ 1) analyses kaydı
    db.collection("analyses").document(analysis_id).set(analysis_doc)

    # ✅ 2) job_queue kaydı: worker buradan okuyacak (tek doküman yeterli)
    # Worker tarafında sorgu: where(status=='queued').order_by(created_at).limit(1)
    db.collection("job_queue").document(analysis_id).set({
        "id": analysis_id,
        "token": token,
        "status": "queued",
        "created_at": now,
        "images": saved_images,
    })

    return {"id": analysis_id, "status": "queued"}

# -------------------------------------------------------------------
# Get Job (Report Page)
# -------------------------------------------------------------------
@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    doc = db.collection("analyses").document(job_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Job not found")
    return doc.to_dict()

# -------------------------------------------------------------------
# Worker: complete job
# -------------------------------------------------------------------
@app.post("/jobs/{job_id}/complete")
async def complete_job(job_id: str, payload: Dict[str, Any]):
    ref = db.collection("analyses").document(job_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Job not found")

    ref.update({
        "status": "done",
        "result": payload,
        "completed_at": utcnow(),
        "error": None,
    })

    # Kuyruktan düş
    db.collection("job_queue").document(job_id).delete()

    return {"ok": True}

# -------------------------------------------------------------------
# Worker: fail job
# -------------------------------------------------------------------
@app.post("/jobs/{job_id}/fail")
async def fail_job(job_id: str, payload: Dict[str, Any]):
    ref = db.collection("analyses").document(job_id)
    snap = ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Job not found")

    ref.update({
        "status": "failed",
        "error": payload,
        "failed_at": utcnow(),
    })

    # Kuyruktan düş
    db.collection("job_queue").document(job_id).delete()

    return {"ok": True}

# -------------------------------------------------------------------
# Optional: quick debug endpoint to see if queue has items
# (Prod'da kaldırabilirsin)
# -------------------------------------------------------------------
@app.get("/debug/queue_count")
def queue_count():
    docs = db.collection("job_queue").where("status", "==", "queued").limit(50).stream()
    c = sum(1 for _ in docs)
    return {"queued": c}
