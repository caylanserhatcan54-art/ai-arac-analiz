# backend/main.py
import os
import json
import uuid
import time
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

APP_ENV = os.getenv("APP_ENV", "prod")
BASE_URL = os.getenv("BASE_URL", "https://ai-arac-analiz-backend.onrender.com").rstrip("/")
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://carvix-web.vercel.app,http://localhost:3000,http://127.0.0.1:3000"
).split(",")

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FLOWS_PATH = DATA_DIR / "flows.json"
JOBS_PATH = DATA_DIR / "jobs.json"

def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

flows: Dict[str, Any] = _load_json(FLOWS_PATH, {})
jobs: Dict[str, Any] = _load_json(JOBS_PATH, {})

def now_ts() -> int:
    return int(time.time())

def safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in [".jpg", ".jpeg", ".png", ".webp", ".mp3", ".wav", ".m4a", ".mp4"]:
        return ext
    return ".bin"

def make_public_upload_url(stored_name: str) -> str:
    # StaticFiles => /uploads/{stored_name}
    return f"{BASE_URL}/uploads/{stored_name}"

app = FastAPI(title="Carvix Backend", version="1.0.0")

# ✅ CORS (kritik)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Uploads statik serve (kritik)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

@app.get("/health")
def health():
    return {"ok": True, "env": APP_ENV}

# -----------------------------
# FLOW: web tarafı bu token ile upload yapar
# -----------------------------
@app.post("/flows")
def create_flow():
    flow_token = str(uuid.uuid4())
    flows[flow_token] = {
        "token": flow_token,
        "created_at": now_ts(),
        "parts": {},          # part_key -> list of image urls
        "audio": None,        # audio url
        "status": "collecting",
        "report": None,
    }
    _save_json(FLOWS_PATH, flows)
    return {"token": flow_token}

# Kullanıcının parça seçip upload etmesi:
# part_key örn: "front_left_door", "hood", "rear_bumper", "hinge_bolts", "overall_left"...
@app.post("/flows/{flow_token}/upload")
async def upload_images(
    flow_token: str,
    part_key: str = Form(...),
    files: List[UploadFile] = File(...),
):
    flow = flows.get(flow_token)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    if part_key not in flow["parts"]:
        flow["parts"][part_key] = []

    for f in files:
        ext = safe_ext(f.filename or "file.bin")
        stored = f"{uuid.uuid4()}{ext}"
        content = await f.read()
        (UPLOAD_DIR / stored).write_bytes(content)
        flow["parts"][part_key].append(make_public_upload_url(stored))

    flows[flow_token] = flow
    _save_json(FLOWS_PATH, flows)
    return {"ok": True, "token": flow_token, "part_key": part_key, "count": len(files), "parts": flow["parts"]}

@app.post("/flows/{flow_token}/upload-audio")
async def upload_audio(
    flow_token: str,
    audio: UploadFile = File(...),
):
    flow = flows.get(flow_token)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    ext = safe_ext(audio.filename or "audio.bin")
    stored = f"{uuid.uuid4()}{ext}"
    (UPLOAD_DIR / stored).write_bytes(await audio.read())
    flow["audio"] = make_public_upload_url(stored)

    flows[flow_token] = flow
    _save_json(FLOWS_PATH, flows)
    return {"ok": True, "token": flow_token, "audio": flow["audio"]}

# Flow'u analize gönder (job oluştur)
@app.post("/flows/{flow_token}/submit")
def submit_flow(flow_token: str):
    flow = flows.get(flow_token)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    if not flow["parts"]:
        raise HTTPException(status_code=400, detail="No images uploaded")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "flow_token": flow_token,
        "created_at": now_ts(),
        "status": "queued",      # queued -> processing -> done/failed
        "claimed_at": None,
        "result": None,
        "error": None,
    }
    flow["status"] = "queued"
    flows[flow_token] = flow

    _save_json(JOBS_PATH, jobs)
    _save_json(FLOWS_PATH, flows)

    return {"ok": True, "job_id": job_id, "flow_token": flow_token}

# -----------------------------
# WORKER: job alma/verme sözleşmesi (Vast.ai)
# -----------------------------
@app.get("/jobs/next")
def get_next_job(worker_key: Optional[str] = None):
    # basit queue: ilk queued job
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
                break

            # ✅ Worker'ın beklediği net sözleşme
            # images: [{part_key, urls:[...]}, ...]
            images_payload = [{"part_key": pk, "urls": urls} for pk, urls in flow["parts"].items()]
            return {
                "id": j["id"],
                "flow_token": j["flow_token"],
                "images": images_payload,
                "audio": flow.get("audio"),
                "base_url": BASE_URL,
            }

    return JSONResponse({"id": None}, status_code=204)

@app.post("/jobs/{job_id}/result")
def submit_job_result(job_id: str, payload: Dict[str, Any]):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")

    j["status"] = "done"
    j["result"] = payload
    jobs[job_id] = j
    _save_json(JOBS_PATH, jobs)

    flow_token = j["flow_token"]
    flow = flows.get(flow_token)
    if flow:
        flow["status"] = "done"
        flow["report"] = payload
        flows[flow_token] = flow
        _save_json(FLOWS_PATH, flows)

    return {"ok": True}

@app.post("/jobs/{job_id}/failed")
def submit_job_failed(job_id: str, payload: Dict[str, Any]):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")

    j["status"] = "failed"
    j["error"] = payload
    jobs[job_id] = j
    _save_json(JOBS_PATH, jobs)

    flow_token = j["flow_token"]
    flow = flows.get(flow_token)
    if flow:
        flow["status"] = "failed"
        flows[flow_token] = flow
        _save_json(FLOWS_PATH, flows)

    return {"ok": True}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j

@app.get("/reports/{flow_token}")
def get_report(flow_token: str):
    flow = flows.get(flow_token)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return {
        "token": flow_token,
        "status": flow["status"],
        "parts": flow["parts"],
        "audio": flow.get("audio"),
        "report": flow.get("report"),
    }
