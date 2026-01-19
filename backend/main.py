import os
import json
import uuid
import time
import requests
import hmac
import hashlib
import base64
import gzip
import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi import Body
from dotenv import load_dotenv

# PDF Kütüphanesi
from xhtml2pdf import pisa 

load_dotenv()

# =========================================================
# ENV & AYARLAR
# =========================================================
APP_ENV = os.getenv("APP_ENV", "prod")
BASE_URL = os.getenv("BASE_URL", "https://ai-arac-analiz-backend.onrender.com").rstrip("/")
ALLOWED_ORIGINS = ["*"] # Test aşamasında CORS sorununu kökten çözmek için
LEMON_SQUEEZY_WEBHOOK_SECRET = os.getenv("LEMON_SQUEEZY_WEBHOOK_SECRET", "")
TAMI_API_URL = "https://api.tami.com.tr/v1/payment/init"
TAMI_MERCHANT_NO = "77019267"
TAMI_TERMINAL_NO = "84019269"
TAMI_SECRET_KEY = os.getenv("TAMI_SECRET_KEY", "25a3ce26-f318-438e-ad7c-1100e8d6fc60")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "carvix.site@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "bfgr qaqu upmy ifcy") 

DATA_DIR = Path("./data")
UPLOAD_DIR = Path("./uploads")
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
FLOWS_PATH = DATA_DIR / "flows.json"
JOBS_PATH = DATA_DIR / "jobs.json"

VEHICLE_CONFIGS = {
    "Otomobil": {"base_img": "https://www.carvix.site/car-base.png", "label": "Binek Araç"},
    "Motosiklet": {"base_img": "https://www.carvix.site/moto-base.png", "label": "Motosiklet"},
    "Pickup": {"base_img": "https://www.carvix.site/pickup-base.png", "label": "Pickup"},
    "Van": {"base_img": "https://www.carvix.site/van-base.png", "label": "Ticari Araç"},
    "ATV": {"base_img": "https://www.carvix.site/atv-base.png", "label": "ATV / Arazi"}
}

# =========================================================
# HELPERS
# =========================================================
def _load_json(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except: return default

def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def now_ts(): return int(time.time())

def safe_ext(filename: str):
    ext = Path(filename).suffix.lower()
    return ext if ext in [".jpg", ".jpeg", ".png", ".webp", ".mp4"] else ".bin"

def generate_tami_signature(m, t, s):
    text = f"{m}{t}{s}"
    return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()

def make_public_upload_url(filename: str):
    return f"{BASE_URL}/uploads/{filename}"

# =========================================================
# PDF ÜRETME
# =========================================================
def create_pdf_report(flow_token: str, report_data: Any, vehicle_type: str = "Otomobil"):
    try:
        config = VEHICLE_CONFIGS.get(vehicle_type, VEHICLE_CONFIGS["Otomobil"])
        parts_analysis = report_data.get('parts_analysis', [])
        ai_comment = report_data.get('ai_comment', "Araç genel durumu incelenmiştir.")
        
        rows_html = ""
        for p in parts_analysis:
            dot_color = "#16a34a" if "ORİJİNAL" in p['status'].upper() else ("#ca8a04" if "BOYALI" in p['status'].upper() else "#dc2626")
            rows_html += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;"><span style="color:#2563eb; margin-right:5px;">●</span> {p['name']}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;"><span style="color:{dot_color}; font-weight:bold;">● {p['status']}</span></td>
                <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; color:#6b7280; font-size:10px;">{p.get('note', '-')}</td>
            </tr>"""

        html_template = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{ size: A4; margin: 0; }}
                body {{ font-family: Helvetica, sans-serif; background-color: #1a1a1a; margin: 0; padding: 40px; }}
                .container {{ background-color: white; border-radius: 20px; padding: 30px; width: 90%; margin: auto; }}
                .header-top {{ display: flex; justify-content: space-between; align-items: center; color: white; margin-bottom: 20px; }}
                .title-main {{ font-size: 28px; font-weight: bold; color: white; }}
                .carvix-logo {{ font-size: 24px; font-weight: 900; color: #3b82f6; }}
                .info-bar {{ background: rgba(255,255,255,0.1); padding: 10px; border-radius: 10px; color: #ccc; font-size: 11px; margin-bottom: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th {{ background: #f3f4f6; color: #4b5563; padding: 12px; text-align: left; font-size: 12px; }}
                .ai-comment-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 15px; margin-top: 20px; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header-top">
                <span class="title-main">Yapay Zeka Özeti</span>
                <span class="carvix-logo">C CARVIX AI</span>
            </div>
            <div class="info-bar">
                Rapor No: {flow_token[:12].upper()} | Tarih: {time.strftime('%d.%m.%Y')}
            </div>
            <div class="container">
                <div style="font-size: 18px; font-weight: bold; margin-bottom: 10px;">ANALİZ ÖZETİ</div>
                <div style="margin-top: 15px; font-size: 13px; color: #374151;">{ai_comment}</div>
                <div style="text-align: center; margin: 20px 0;">
                    <img src="{config['base_img']}" style="width: 380px;">
                </div>
                <table>
                    <thead><tr><th>Parça</th><th>Durum</th><th>Notlar</th></tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
        </body>
        </html>
        """
        result_file = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_template), dest=result_file)
        return result_file.getvalue()
    except Exception as e:
        print(f"PDF Error: {e}"); return None

# =========================================================
# MAİL FONKSİYONU
# =========================================================
def send_report_email(customer_email: str, flow_token: str, report_content: Any, vehicle_type: str = "Otomobil"):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = customer_email
        msg['Subject'] = f"Carvix AI - {vehicle_type} Raporunuz Hazır!"
        msg.attach(MIMEText(f"Aracınızın analizi tamamlandı. Detaylar ektedir.", 'plain'))
        pdf_data = create_pdf_report(flow_token, report_content, vehicle_type)
        if pdf_data:
            attachment = MIMEApplication(pdf_data, _subtype="pdf")
            attachment.add_header('Content-Disposition', 'attachment', filename=f"Carvix_Rapor.pdf")
            msg.attach(attachment)
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Mail gönderme hatası: {e}"); return False

# =========================================================
# APP & ENDPOINTS
# =========================================================
flows = _load_json(FLOWS_PATH, {})
jobs = _load_json(JOBS_PATH, {})

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

@app.post("/api/payment/shopier-callback")
async def shopier_callback(request: Request):
    try:
        form_data = await request.form()
        res_data = dict(form_data)
        if res_data.get("res_status") == "success":
            customer_email = res_data.get("res_mail")
            for f_token, f_data in flows.items():
                if f_data.get("email") == customer_email:
                    flows[f_token]["status"] = "paid"
                    _save_json(FLOWS_PATH, flows)
                    if f_data.get("report"):
                        send_report_email(customer_email, f_token, f_data["report"], f_data.get("vehicle_type", "Otomobil"))
                    break
        return Response(content="OK", status_code=200)
    except Exception as e:
        return Response(content="FAILED", status_code=500)

@app.post("/flows")
async def create_flow(payload: Dict[str, Any] = Body(default={})):
    token = str(uuid.uuid4())
    flows[token] = {"token": token, "vehicle_type": payload.get("vehicle_type", "Otomobil"), "created_at": now_ts(), "parts": {}, "status": "collecting", "report": None, "email": None}
    _save_json(FLOWS_PATH, flows); return {"token": token}

@app.post("/flows/{flow_token}/upload")
async def upload_images(flow_token: str, part_key: str = Form(...), files: List[UploadFile] = File(...)):
    flow = flows.get(flow_token)
    if not flow: raise HTTPException(404)
    if part_key not in flow["parts"]: flow["parts"][part_key] = []
    for f in files:
        stored = f"{uuid.uuid4()}{safe_ext(f.filename)}"
        (UPLOAD_DIR / stored).write_bytes(await f.read())
        flow["parts"][part_key].append(make_public_upload_url(stored))
    _save_json(FLOWS_PATH, flows); return {"ok": True}

@app.post("/flows/{flow_token}/submit")
async def submit_flow(flow_token: str, payload: Dict[str, Any] = Body(...)):
    flow = flows.get(flow_token)
    if not flow: raise HTTPException(404)
    flow["email"] = payload.get("email")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"id": job_id, "flow_token": flow_token, "status": "queued"}
    flow["status"] = "queued"
    _save_json(JOBS_PATH, jobs); _save_json(FLOWS_PATH, flows)
    return {"ok": True, "job_id": job_id}

@app.get("/jobs/next")
def get_next_job():
    for jid, j in jobs.items():
        if j["status"] == "queued":
            j["status"] = "processing"
            _save_json(JOBS_PATH, jobs)
            flow = flows.get(j["flow_token"])
            return {"id": jid, "flow_token": j["flow_token"], "vehicle_type": flow.get("vehicle_type", "Otomobil"), "images": flow["parts"]}
    return Response(status_code=204)

@app.post("/jobs/{job_id}/result")
def submit_job_result(job_id: str, payload: Dict[str, Any]):
    j = jobs.get(job_id)
    if not j: return {"error": "Job not found"}
    j["status"] = "done"; j["result"] = payload
    flow = flows.get(j["flow_token"])
    if flow:
        flow["status"] = "done"; flow["report"] = payload
        _save_json(FLOWS_PATH, flows)
        if flow.get("email"):
            send_report_email(flow["email"], j["flow_token"], payload, flow.get("vehicle_type", "Otomobil"))
    _save_json(JOBS_PATH, jobs); return {"ok": True}

# KRİTİK EKLENTİ: AI HATA ALIRSA BURAYA GELECEK
@app.post("/jobs/{job_id}/failed")
def job_failed(job_id: str, payload: Dict[str, Any] = Body(...)):
    print(f"DEBUG: AI Hatası - Job ID: {job_id} - Sebep: {payload.get('error')}")
    j = jobs.get(job_id)
    if j:
        j["status"] = "error"; j["error_details"] = payload.get("error")
        _save_json(JOBS_PATH, jobs)
    return {"ok": True}

@app.get("/reports/{flow_token}")
def get_report(flow_token: str):
    flow = flows.get(flow_token)
    if not flow: raise HTTPException(404)
    return {"token": flow_token, "status": flow["status"], "report": flow.get("report")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)