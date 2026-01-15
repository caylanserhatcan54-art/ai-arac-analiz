import os
import json
import uuid
import time
import requests
import hmac
import hashlib
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body
from dotenv import load_dotenv
load_dotenv()

# =========================================================
# ENV
# =========================================================
APP_ENV = os.getenv("APP_ENV", "prod")
BASE_URL = os.getenv(
    "BASE_URL",
    "https://ai-arac-analiz-backend.onrender.com"
).rstrip("/")

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://www.carvix.site,http://localhost:3000,http://127.0.0.1:3000"
).split(",")

# Lemon Squeezy Secret (Panelden alacağın şifre)
LEMON_SQUEEZY_WEBHOOK_SECRET = os.getenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "")

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FLOWS_PATH = DATA_DIR / "flows.json"
JOBS_PATH = DATA_DIR / "jobs.json"

# =========================================================
# HELPERS
# =========================================================
def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _save_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def now_ts() -> int:
    return int(time.time())

def safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in [".jpg", ".jpeg", ".png", ".webp", ".mp3", ".wav", ".m4a", ".mp4"]:
        return ext
    return ".bin"

def make_public_upload_url(stored_name: str) -> str:
    return f"{BASE_URL}/uploads/{stored_name}"

# =========================================================
# STATE (FILE BASED)
# =========================================================
flows: Dict[str, Any] = _load_json(FLOWS_PATH, {})
jobs: Dict[str, Any] = _load_json(JOBS_PATH, {})

# =========================================================
# APP
# =========================================================
app = FastAPI(title="Carvix Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# =========================================================
# HEALTH
# =========================================================
@app.get("/health")
def health():
    return {"ok": True, "env": APP_ENV}

# =========================================================
# LEMON SQUEEZY WEBHOOK (YENİ EKLENDİ)
# =========================================================
@app.post("/webhook/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request):
    # 1. Güvenlik Kontrolü (İsteğe bağlı ama önerilir)
    body = await request.body()
    # Not: Gerçek ortamda hmac doğrulaması buraya eklenir.

    try:
        data = json.loads(body)
    except:
        raise HTTPException(400, "Invalid JSON")

    event_name = data.get("meta", {}).get("event_name")
    
    # Sadece ödeme başarılı olduğunda işlem yap
    if event_name == "order_created":
        # Bizim ödeme linkine eklediğimiz token bilgisini alıyoruz
        custom_data = data.get("meta", {}).get("custom_data", {})
        flow_token = custom_data.get("token")

        if flow_token and flow_token in flows:
            print(f"PAYMENT SUCCESS: Flow {flow_token} is now PAID.")
            # Flow durumunu güncelle
            flows[flow_token]["status"] = "paid" 
            _save_json(FLOWS_PATH, flows)
            
            # Eğer bu flow'a bağlı bir job varsa onu da 'paid' yapabiliriz
            for jid, job in jobs.items():
                if job["flow_token"] == flow_token:
                    job["status"] = "paid"
                    _save_json(JOBS_PATH, jobs)

    return {"ok": True}

# =========================================================
# FLOW CREATE
# =========================================================
@app.post("/flows")
def create_flow():
    token = str(uuid.uuid4())
    flows[token] = {
        "token": token,
        "created_at": now_ts(),
        "parts": {},
        "audio": None,
        "status": "collecting",
        "report": None,
    }
    _save_json(FLOWS_PATH, flows)
    return {"token": token}

# =========================================================
# FLOW IMAGE UPLOAD (PARÇA BAZLI)
# =========================================================
@app.post("/flows/{flow_token}/upload")
async def upload_images(
    flow_token: str,
    part_key: str = Form(...),
    files: List[UploadFile] = File(...),
):
    flow = flows.get(flow_token)

    if not flow:
        flows[flow_token] = {
            "token": flow_token,
            "created_at": now_ts(),
            "parts": {},
            "audio": None,
            "status": "collecting",
            "report": None,
        }
        flow = flows[flow_token]

    if part_key not in flow["parts"]:
        flow["parts"][part_key] = []

    for f in files:
        ext = safe_ext(f.filename or "file.bin")
        stored = f"{uuid.uuid4()}{ext}"
        (UPLOAD_DIR / stored).write_bytes(await f.read())
        flow["parts"][part_key].append(make_public_upload_url(stored))

    flows[flow_token] = flow
    _save_json(FLOWS_PATH, flows)

    return {
        "ok": True,
        "token": flow_token,
        "part_key": part_key,
        "count": len(files),
    }

# =========================================================
# FLOW AUDIO UPLOAD
# =========================================================
@app.post("/flows/{flow_token}/upload-audio")
async def upload_audio(
    flow_token: str,
    audio: UploadFile = File(...),
):
    flow = flows.get(flow_token)
    if not flow:
        raise HTTPException(404, "Flow not found")

    ext = safe_ext(audio.filename or "audio.bin")
    stored = f"{uuid.uuid4()}{ext}"
    (UPLOAD_DIR / stored).write_bytes(await audio.read())

    flow["audio"] = make_public_upload_url(stored)
    flows[flow_token] = flow
    _save_json(FLOWS_PATH, flows)

    return {"ok": True, "audio": flow["audio"]}

# =========================================================
# FLOW SUBMIT → JOB CREATE
# =========================================================
@app.post("/flows/{flow_token}/submit")
def submit_flow(flow_token: str):
    flow = flows.get(flow_token)
    if not flow:
        raise HTTPException(404, "Flow not found")

    if not flow.get("parts"):
        raise HTTPException(400, "No images uploaded")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "flow_token": flow_token,
        "created_at": now_ts(),
        "status": "queued",
        "claimed_at": None,
        "result": None,
        "error": None,
    }

    flow["status"] = "queued"
    flows[flow_token] = flow

    _save_json(JOBS_PATH, jobs)
    _save_json(FLOWS_PATH, flows)

    return {"ok": True, "job_id": job_id}

# =========================================================
# FRONTEND COMPAT: /jobs (OLD FLOW)
# =========================================================
@app.post("/jobs")
async def create_job_compat(
    token: str = Form(...),
    views: str = Form(...),
    files: List[UploadFile] = File(...),
):
    flow = flows.setdefault(token, {
        "token": token,
        "created_at": now_ts(),
        "parts": {},
        "audio": None,
        "status": "collecting",
        "report": None,
    })

    try:
        views_data = json.loads(views)
    except Exception:
        raise HTTPException(400, "views parse error")

    name_to_part = {
        (v.get("filename") or "").strip(): (v.get("part") or "").strip()
        for v in views_data
        if v.get("filename") and v.get("part")
    }

    for f in files:
        part = name_to_part.get(f.filename, "UNKNOWN")
        flow["parts"].setdefault(part, [])

        ext = safe_ext(f.filename or "file.bin")
        stored = f"{uuid.uuid4()}{ext}"
        (UPLOAD_DIR / stored).write_bytes(await f.read())
        flow["parts"][part].append(make_public_upload_url(stored))

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "flow_token": token,
        "created_at": now_ts(),
        "status": "queued",
        "claimed_at": None,
        "result": None,
        "error": None,
    }

    flow["status"] = "queued"
    flows[token] = flow

    _save_json(FLOWS_PATH, flows)
    _save_json(JOBS_PATH, jobs)

    return {"id": job_id, "ok": True}

# =========================================================
# WORKER: JOB FETCH
# =========================================================
@app.get("/jobs/next")
def get_next_job():
    for jid, j in jobs.items():
        if j["status"] == "queued":
            j["status"] = "processing"
            j["claimed_at"] = now_ts()
            jobs[jid] = j
            _save_json(JOBS_PATH, jobs)

            flow = flows.get(j["flow_token"])
            if not flow:
                j["status"] = "failed"
                j["error"] = "Flow missing"
                jobs[jid] = j
                _save_json(JOBS_PATH, jobs)
                return JSONResponse({"id": None}, status_code=204)

            images = [
                {"part_key": k, "urls": v}
                for k, v in flow.get("parts", {}).items()
            ]

            return {
                "id": j["id"],
                "flow_token": j["flow_token"],
                "images": images,
                "audio": flow.get("audio"),
                "base_url": BASE_URL,
            }

    return JSONResponse({"id": None}, status_code=204)

# =========================================================
# WORKER RESULT
# =========================================================
@app.post("/jobs/{job_id}/result")
def submit_job_result(job_id: str, payload: Dict[str, Any]):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")

    j["status"] = "done"
    j["result"] = payload
    jobs[job_id] = j

    flow = flows.get(j["flow_token"])
    if flow:
        flow["status"] = "done"
        flow["report"] = payload
        flows[j["flow_token"]] = flow
        _save_json(FLOWS_PATH, flows)

    _save_json(JOBS_PATH, jobs)
    return {"ok": True}

# =========================================================
# JOB STATUS
# =========================================================
@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return j

# =========================================================
# REPORT
# =========================================================
@app.get("/reports/{flow_token}")
def get_report(flow_token: str):
    flow = flows.get(flow_token)
    if not flow:
        raise HTTPException(404, "Flow not found")
    return {
        "token": flow_token,
        "status": flow["status"],
        "parts": flow.get("parts"),
        "audio": flow.get("audio"),
        "report": flow.get("report"),
    }