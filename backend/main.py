from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os, json, uuid, shutil

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
JOBS_FILE = os.path.join(BASE_DIR, "jobs_queue.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)

if not os.path.exists(JOBS_FILE):
    with open(JOBS_FILE, "w") as f:
        json.dump({}, f)

# =========================
# APP
# =========================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://carvix-web.vercel.app",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 STATIC FILES (ÇOK KRİTİK)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# =========================
# UPLOAD IMAGES
# =========================
@app.post("/analysis/{token}/images")
async def upload_images(token: str, images: list[UploadFile] = File(...)):
    urls = []
    for img in images:
        filename = f"{uuid.uuid4()}_{img.filename}"
        path = os.path.join(UPLOAD_DIR, filename)
        with open(path, "wb") as f:
            shutil.copyfileobj(img.file, f)
        urls.append(f"https://ai-arac-analiz-backend.onrender.com/uploads/{filename}")
    return {"images": urls}

# =========================
# CREATE JOB
# =========================
@app.post("/jobs/create")
def create_job(payload: dict):
    with open(JOBS_FILE, "r") as f:
        jobs = json.load(f)

    job_id = payload["job_id"]

    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "images": payload["images"]
    }

    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

    return {"ok": True, "job_id": job_id}

# =========================
# WORKER POLL
# =========================
@app.get("/jobs/next")
def next_job():
    with open(JOBS_FILE, "r") as f:
        jobs = json.load(f)

    for job in jobs.values():
        if job["status"] == "pending":
            job["status"] = "processing"
            with open(JOBS_FILE, "w") as f:
                json.dump(jobs, f, indent=2)
            return {"job": job}

    return {"job": None}

# =========================
# SAVE RESULT
# =========================
@app.post("/jobs/{job_id}/result")
def save_result(job_id: str, payload: dict):
    with open(JOBS_FILE, "r") as f:
        jobs = json.load(f)

    jobs[job_id]["status"] = "done"
    jobs[job_id]["result"] = payload

    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

    return {"ok": True}

# =========================
# GET JOB
# =========================
@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    with open(JOBS_FILE, "r") as f:
        jobs = json.load(f)

    return jobs.get(job_id, {"status": "not_found"})
