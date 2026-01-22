import os
import json
import uuid
import time
import requests
import hashlib
import base64
import smtplib
import io
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
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
    "Pickup": {"base_img": "https://www.carvix.site/pickup-base.png", "label": "Pickup / Kamyonet"},
    "Van": {"base_img": "https://www.carvix.site/van-base.png", "label": "Ticari Araç"},
    "ATV": {"base_img": "https://www.carvix.site/atv-base.png", "label": "ATV / Arazi Aracı"},
    "Elektrikli": {"base_img": "https://www.carvix.site/car-base.png", "label": "Elektrikli Araç"}
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

def make_public_upload_url(filename: str):
    return f"{BASE_URL}/uploads/{filename}"

# =========================================================
# MODERN PDF ÜRETME (GELİŞMİŞ EKSPER FORMATI)
# =========================================================
def create_pdf_report(flow_token: str, report_data: Any, vehicle_type: str = "Otomobil"):
    try:
        config = VEHICLE_CONFIGS.get(vehicle_type, VEHICLE_CONFIGS["Otomobil"])
        parts_analysis = report_data.get('parts_analysis', [])
        ai_comment = report_data.get('ai_comment', "Analiz başarıyla tamamlandı.")
        plate = report_data.get('plate', 'BELİRLENEMEDİ')
        
        rows_html = ""
        for p in parts_analysis:
            status = p['status'].upper()
            # Kritik=Kırmızı, Gözlem=Turuncu, Sağlıklı=Yeşil
            color = "#dc2626" if "KRITIK" in status else ("#f59e0b" if "GOZLEM" in status else "#10b981")
            
            score_match = re.search(r'%(\d+)', p.get('note', '0'))
            score_val = int(score_match.group(1)) if score_match else 0
            
            rows_html += f"""
            <tr style="border-bottom: 1px solid #edf2f7;">
                <td style="padding: 12px; font-weight: bold; color: #1e293b; font-size: 11px;">{p['name']}</td>
                <td style="padding: 12px;">
                    <span style="color: {color}; font-weight: bold; font-size: 10px;">● {status}</span>
                </td>
                <td style="padding: 12px;">
                    <div style="font-size: 9px; color: #64748b; margin-bottom: 2px;">{p.get('note', '-')}</div>
                    <div style="width: 80px; background: #e2e8f0; height: 5px; border-radius: 3px;">
                        <div style="width: {score_val}%; background: {color}; height: 5px; border-radius: 3px;"></div>
                    </div>
                </td>
            </tr>"""

        # HTML Şablonu - Türkçe Karakter ve Modern Arayüz Fix
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <style>
                @page {{ size: A4; margin: 0; }}
                body {{ font-family: 'Helvetica', 'Arial', sans-serif; background-color: #f8fafc; margin: 0; padding: 0; color: #1e293b; }}
                
                .header-gradient {{ background: #0f172a; color: #ffffff; padding: 40px 20px; text-align: center; border-bottom: 4px solid #3b82f6; }}
                .brand-title {{ font-size: 26px; font-weight: bold; letter-spacing: 2px; color: #3b82f6; }}
                
                .container {{ width: 88%; margin: -30px auto 0; background: #ffffff; border-radius: 12px; padding: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); }}
                
                .info-bar {{ display: table; width: 100%; border-bottom: 1px solid #e2e8f0; padding-bottom: 15px; margin-bottom: 20px; }}
                .info-item {{ display: table-cell; width: 33.3%; font-size: 11px; }}
                .info-label {{ color: #64748b; text-transform: uppercase; font-size: 9px; font-weight: bold; }}
                .info-value {{ color: #0f172a; font-weight: bold; font-size: 12px; }}

                .ai-section {{ background: #f0f9ff; border-radius: 8px; padding: 15px; border-left: 4px solid #3b82f6; margin-bottom: 25px; }}
                .section-title {{ font-size: 13px; font-weight: bold; color: #0f172a; margin-bottom: 10px; text-transform: uppercase; border-bottom: 1px solid #3b82f6; display: inline-block; }}

                table {{ width: 100%; border-collapse: collapse; }}
                th {{ text-align: left; font-size: 10px; color: #64748b; padding: 10px; background: #f1f5f9; text-transform: uppercase; }}
                
                .footer {{ text-align: center; padding: 25px; color: #94a3b8; font-size: 9px; line-height: 1.4; }}
                .car-schema {{ text-align: center; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="header-gradient">
                <div class="brand-title">CARVIX AI</div>
                <div style="font-size: 12px; opacity: 0.8; margin-top: 5px;">OTONOM ARAÇ EKSPERTİZ RAPORU</div>
            </div>

            <div class="container">
                <div class="info-bar">
                    <div class="info-item">
                        <div class="info-label">ARAÇ PLAKASI</div>
                        <div class="info-value">{plate}</div>
                    </div>
                    <div class="info-item" style="text-align: center;">
                        <div class="info-label">ARAÇ TÜRÜ</div>
                        <div class="info-value">{config['label']}</div>
                    </div>
                    <div class="info-item" style="text-align: right;">
                        <div class="info-label">RAPOR TARİHİ</div>
                        <div class="info-value">{time.strftime('%d.%m.%Y %H:%M')}</div>
                    </div>
                </div>

                <div class="section-title">YAPAY ZEKA ANALİZ ÖZETİ</div>
                <div class="ai-section">
                    <div style="font-size: 11px; line-height: 1.6; color: #1e293b;">{ai_comment}</div>
                </div>

                <div class="car-schema">
                    <img src="{config['base_img']}" style="width: 380px;">
                    <div style="font-size: 8px; color: #cbd5e1; margin-top: 5px;">* Dijital Hasar Dağılım Şeması</div>
                </div>

                <div class="section-title">DETAYLI EKSPERTİZ LİSTESİ</div>
                <table>
                    <thead>
                        <tr>
                            <th>BÖLGE / PARÇA</th>
                            <th>DURUM</th>
                            <th>ANALİZ VERİSİ & GÜVEN</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>

            <div class="footer">
                <strong>YASAL UYARI:</strong> Bu rapor Carvix AI tarafından üretilen bir ön analizdir. 
                Kesin sonuçlar için TSE onaylı fiziksel muayene yapılması önerilir.<br>
                <span style="color: #3b82f6; font-weight: bold; font-size: 11px;">www.carvix.site</span>
                <div style="margin-top: 10px; opacity: 0.5;">ID: {flow_token.upper()}</div>
            </div>
        </body>
        </html>
        """
        result_file = io.BytesIO()
        # UTF-8 Encoding buradaki en kritik parça
        pisa.CreatePDF(io.BytesIO(html_template.encode("utf-8")), dest=result_file, encoding='utf-8')
        return result_file.getvalue()
    except Exception as e:
        print(f"PDF Hatası: {e}"); return None

# =========================================================
# MAİL FONKSİYONU
# =========================================================
def send_report_email(customer_email: str, flow_token: str, report_content: Any, vehicle_type: str = "Otomobil"):
    try:
        msg = MIMEMultipart()
        msg['From'] = f"Carvix AI <{SENDER_EMAIL}>"
        msg['To'] = customer_email
        msg['Subject'] = f"Ekspertiz Raporunuz Hazır - {vehicle_type}"
        
        body = f"Sayın Müşterimiz,\n\nAracınız için yapılan yapay zeka destekli analiz tamamlanmıştır. Detaylı raporunuz ekteki PDF dosyasında yer almaktadır.\n\nBizi tercih ettiğiniz için teşekkür ederiz.\n\nCarvix AI Ekibi"
        msg.attach(MIMEText(body, 'plain'))

        pdf_data = create_pdf_report(flow_token, report_content, vehicle_type)
        if pdf_data:
            attachment = MIMEApplication(pdf_data, _subtype="pdf")
            attachment.add_header('Content-Disposition', 'attachment', filename=f"Carvix_Ekspertiz_Raporu.pdf")
            msg.attach(attachment)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Mail Hatası: {e}"); return False

# =========================================================
# APP & ENDPOINTS
# =========================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

flows = _load_json(FLOWS_PATH, {})
jobs = _load_json(JOBS_PATH, {})

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

@app.post("/flows")
async def create_flow(payload: Dict[str, Any] = Body(default={})):
    token = str(uuid.uuid4())
    flows[token] = {
        "token": token, 
        "vehicle_type": payload.get("vehicle_type", "Otomobil"), 
        "created_at": now_ts(), 
        "parts": {}, 
        "status": "collecting", 
        "report": None, 
        "email": None
    }
    _save_json(FLOWS_PATH, flows)
    return {"token": token}

@app.post("/flows/{flow_token}/upload")
async def upload_images(flow_token: str, part_key: str = Form(...), files: List[UploadFile] = File(...)):
    flow = flows.get(flow_token)
    if not flow: raise HTTPException(404)
    if part_key not in flow["parts"]: flow["parts"][part_key] = []
    for f in files:
        stored = f"{uuid.uuid4()}{safe_ext(f.filename)}"
        (UPLOAD_DIR / stored).write_bytes(await f.read())
        flow["parts"][part_key].append(make_public_upload_url(stored))
    _save_json(FLOWS_PATH, flows)
    return {"ok": True}

@app.post("/flows/{flow_token}/submit")
async def submit_flow(flow_token: str, payload: Dict[str, Any] = Body(...)):
    flow = flows.get(flow_token)
    if not flow: raise HTTPException(404)
    flow["email"] = payload.get("email")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"id": job_id, "flow_token": flow_token, "status": "queued"}
    flow["status"] = "queued"
    _save_json(JOBS_PATH, jobs)
    _save_json(FLOWS_PATH, flows)
    return {"ok": True, "job_id": job_id}

@app.get("/jobs/next")
def get_next_job():
    for jid, j in jobs.items():
        if j["status"] == "queued":
            j["status"] = "processing"
            _save_json(JOBS_PATH, jobs)
            flow = flows.get(j["flow_token"])
            return {
                "id": jid, 
                "flow_token": j["flow_token"], 
                "vehicle_type": flow.get("vehicle_type", "Otomobil"), 
                "images": flow["parts"]
            }
    return Response(status_code=204)

@app.post("/jobs/{job_id}/result")
def submit_job_result(job_id: str, payload: Dict[str, Any]):
    j = jobs.get(job_id)
    if not j: return {"error": "Job not found"}
    
    if not payload.get("parts_analysis") and payload.get("plate") == "Tespit Edilemedi":
        print(f">>> HATA: {job_id} için analiz boş geldi.")
        return {"ok": False, "message": "Analiz verisi boş"}

    j["status"] = "done"
    j["result"] = payload
    flow = flows.get(j["flow_token"])
    if flow:
        flow["status"] = "done"
        flow["report"] = payload
        _save_json(FLOWS_PATH, flows)
        if flow.get("email"):
            send_report_email(flow["email"], j["flow_token"], payload, flow.get("vehicle_type", "Otomobil"))
    _save_json(JOBS_PATH, jobs)
    return {"ok": True}

@app.get("/reports/{flow_token}")
def get_report(flow_token: str):
    flow = flows.get(flow_token)
    if not flow: raise HTTPException(404)
    return {"token": flow_token, "status": flow["status"], "report": flow.get("report")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)