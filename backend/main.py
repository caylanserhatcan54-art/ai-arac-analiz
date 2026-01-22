import os
import json
import uuid
import time
import requests
import hashlib
import base64
import smtplib
import io
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

# Her araç tipi için profesyonel şema eşleşmesi
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
            # Renk Kodları: Kritik=Kırmızı, Gözlem=Turuncu, Diğer=Mavi
            color = "#dc2626" if "KRITIK" in status else ("#f59e0b" if "GOZLEM" in status else "#2563eb")
            
            # SAM Güven Skoru Çubuğu Hesaplama
            # Not içindeki "%" işaretini bulup sayıya çeviriyoruz
            import re
            score_match = re.search(r'%(\d+)', p.get('note', '0'))
            score_val = int(score_match.group(1)) if score_match else 0
            
            rows_html += f"""
            <tr style="border-bottom: 1px solid #edf2f7;">
                <td style="padding: 15px; font-weight: bold; color: #1e293b; font-size: 12px;">{p['name']}</td>
                <td style="padding: 15px;">
                    <span style="color: {color}; font-weight: 800; font-size: 10px;">● {status}</span>
                </td>
                <td style="padding: 15px;">
                    <div style="font-size: 10px; color: #64748b; margin-bottom: 4px;">{p.get('note', '-')}</div>
                    <div style="width: 100px; background: #e2e8f0; height: 6px; border-radius: 3px;">
                        <div style="width: {score_val}%; background: {color}; height: 6px; border-radius: 3px;"></div>
                    </div>
                </td>
            </tr>"""

        html_template = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{ size: A4; margin: 0; }}
                body {{ font-family: Helvetica, Arial, sans-serif; background-color: #ffffff; margin: 0; padding: 0; color: #1e293b; }}
                .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: white; padding: 40px 20px; text-align: center; }}
                .carvix-brand {{ color: #3b82f6; font-size: 28px; font-weight: 900; letter-spacing: -1px; }}
                .badge {{ background: rgba(59, 130, 246, 0.1); color: #3b82f6; padding: 4px 12px; border-radius: 20px; font-size: 10px; font-weight: bold; text-transform: uppercase; }}
                
                .container {{ width: 90%; margin: -30px auto 0; background: white; border-radius: 16px; padding: 30px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); border: 1px solid #f1f5f9; }}
                
                .info-card {{ display: table; width: 100%; margin-bottom: 25px; background: #f8fafc; padding: 15px; border-radius: 12px; }}
                .info-column {{ display: table-cell; width: 33%; }}
                .label {{ font-size: 9px; color: #64748b; text-transform: uppercase; font-weight: bold; }}
                .value {{ font-size: 13px; color: #0f172a; font-weight: 800; }}

                .expert-comment {{ background: #f0f9ff; border-radius: 12px; padding: 20px; border-left: 5px solid #3b82f6; margin-bottom: 30px; }}
                .section-title {{ font-size: 14px; font-weight: 900; color: #0f172a; margin-bottom: 15px; border-bottom: 2px solid #3b82f6; display: inline-block; }}

                table {{ width: 100%; border-collapse: collapse; }}
                th {{ text-align: left; font-size: 10px; color: #64748b; padding: 10px 15px; background: #f1f5f9; text-transform: uppercase; }}
                
                .footer {{ text-align: center; padding: 30px; background: #f8fafc; margin-top: 40px; border-top: 1px solid #e2e8f0; }}
                .warning-text {{ font-size: 8px; color: #94a3b8; line-height: 1.5; max-width: 80%; margin: 0 auto; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="carvix-brand">CARVIX AI</div>
                <div style="font-size: 14px; opacity: 0.8; margin-top: 5px;">OTONOM ARAÇ EKSPERTİZ SİSTEMİ</div>
            </div>

            <div class="container">
                <div class="info-card">
                    <div class="info-column">
                        <div class="label">ARAÇ PLAKASI</div>
                        <div class="value">{plate}</div>
                    </div>
                    <div class="info-column" style="text-align: center;">
                        <div class="label">ARAÇ SEGMENTİ</div>
                        <div class="value">{config['label']}</div>
                    </div>
                    <div class="info-column" style="text-align: right;">
                        <div class="label">RAPOR TARİHİ</div>
                        <div class="value">{time.strftime('%d.%m.%Y %H:%M')}</div>
                    </div>
                </div>

                <div class="section-title">YAPAY ZEKA ANALİZ YORUMU</div>
                <div class="expert-comment">
                    <div style="font-size: 12px; line-height: 1.6; color: #334155;">{ai_comment}</div>
                </div>

                <div style="text-align: center; margin: 30px 0;">
                    <img src="{config['base_img']}" style="width: 420px; opacity: 0.9;">
                    <p style="font-size: 9px; color: #94a3b8;">* Dijital tarama şematik gösterimidir.</p>
                </div>

                <div class="section-title">DETAYLI PARÇA ANALİZİ</div>
                <table>
                    <thead>
                        <tr>
                            <th>BÖLGE / BİLEŞEN</th>
                            <th>DURUM</th>
                            <th>SAM DOĞRULAMA & GÜVEN SKORU</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>

            <div class="footer">
                <div style="margin-bottom: 15px;">
                    <span class="badge">RAPOR ID: {flow_token.upper()}</span>
                </div>
                <div class="warning-text">
                    <strong>YASAL BİLGİLENDİRME:</strong> Bu rapor Carvix AI motoru tarafından üretilmiş bir ön incelemedir. 
                    Işık, kamera açısı ve çevresel faktörler analiz sonuçlarını etkileyebilir. 
                    Resmi işlemler için TSE onaylı fiziksel ekspertiz yaptırılması zorunludur. 
                    Carvix AI, bu raporun kullanımından doğabilecek maddi/manevi zararlardan sorumlu tutulamaz.
                </div>
                <div style="font-size: 10px; font-weight: bold; margin-top: 20px; color: #3b82f6;">www.carvix.site</div>
            </div>
        </body>
        </html>
        """
        result_file = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_template), dest=result_file)
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