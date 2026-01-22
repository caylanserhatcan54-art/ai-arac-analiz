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
# KARAKTER TEMIZLEME FONKSIYONU (S, I, G, O, U YAPAR)
# =========================================================
def clear_tr(text):
    if not text: return ""
    tr_map = str.maketrans("İıŞşĞğÇçÖöÜü", "IiSsGgCcOoUu")
    return str(text).translate(tr_map)

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
    "Otomobil": {"base_img": "https://www.carvix.site/car-base.png", "label": "Binek Arac"},
    "Motosiklet": {"base_img": "https://www.carvix.site/moto-base.png", "label": "Motosiklet"},
    "Pickup": {"base_img": "https://www.carvix.site/pickup-base.png", "label": "Pickup / Kamyonet"},
    "Van": {"base_img": "https://www.carvix.site/van-base.png", "label": "Ticari Arac"},
    "ATV": {"base_img": "https://www.carvix.site/atv-base.png", "label": "ATV / Arazi Araci"},
    "Elektrikli": {"base_img": "https://www.carvix.site/car-base.png", "label": "Elektrikli Arac"}
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
# GÖRSEL DESTEKLİ MODERN PDF ÜRETME
# =========================================================
def create_pdf_report(flow_token: str, report_data: Any, vehicle_type: str = "Otomobil"):
    try:
        config = VEHICLE_CONFIGS.get(vehicle_type, VEHICLE_CONFIGS["Otomobil"])
        parts_analysis = report_data.get('parts_analysis', [])
        ai_comment = clear_tr(report_data.get('ai_comment', "Analiz basariyla tamamlandi."))
        plate = clear_tr(report_data.get('plate', 'BELIRLENEMEDI'))
        
        # ANALİZ KARTLARI (GÖRSEL KANITLI)
        cards_html = ""
        for p in parts_analysis:
            p_name = clear_tr(p['name'])
            status = clear_tr(p['status']).upper()
            note = clear_tr(p.get('note', '-'))
            # Vast.ai'den gelmesi gereken hasarlı resim linki
            img_url = p.get('image_url', '') 
            
            color = "#dc2626" if "KRITIK" in status else ("#f59e0b" if "GOZLEM" in status else "#2563eb")
            score_match = re.search(r'%(\d+)', note)
            score_val = int(score_match.group(1)) if score_match else 0
            
            cards_html += f"""
            <div style="border: 1px solid #e2e8f0; border-radius: 10px; margin-bottom: 20px; padding: 15px; background: #ffffff;">
                <table width="100%">
                    <tr>
                        <td width="60%" style="vertical-align: top;">
                            <div style="font-size: 14px; font-weight: bold; color: #0f172a; margin-bottom: 5px;">{p_name}</div>
                            <div style="color: {color}; font-weight: bold; font-size: 12px; margin-bottom: 10px;">● {status}</div>
                            <div style="font-size: 10px; color: #64748b; margin-bottom: 10px; line-height: 1.4;">{note}</div>
                            <div style="width: 150px; background: #f1f5f9; height: 8px; border-radius: 4px; overflow: hidden;">
                                <div style="width: {score_val}%; background: {color}; height: 8px;"></div>
                            </div>
                            <div style="font-size: 9px; color: #94a3b8; margin-top: 5px;">Yapay Zeka Tespit Guveni: %{score_val}</div>
                        </td>
                        <td width="40%" style="text-align: right; vertical-align: middle;">
                            {f'<img src="{img_url}" style="width: 180px; height: 110px; border-radius: 8px; border: 2px solid #f1f5f9; object-fit: cover;">' if img_url else '<div style="font-size: 10px; color: #cbd5e1; border: 1px dashed #cbd5e1; padding: 20px; text-align:center;">Gorsel Kanit<br>Analiz Ediliyor</div>'}
                        </td>
                    </tr>
                </table>
            </div>"""

        html_template = f"""
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <style>
                @page {{ size: A4; margin: 0; }}
                body {{ font-family: Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 0; color: #1e293b; }}
                .header {{ background: #0f172a; color: #ffffff; padding: 40px 20px; text-align: center; border-bottom: 5px solid #3b82f6; }}
                .container {{ width: 88%; margin: -30px auto 0; background: #ffffff; border-radius: 15px; padding: 30px; box-shadow: 0 10px 20px rgba(0,0,0,0.05); }}
                .info-bar {{ display: table; width: 100%; border-bottom: 2px solid #f1f5f9; padding-bottom: 15px; margin-bottom: 25px; }}
                .info-item {{ display: table-cell; width: 33%; font-size: 12px; }}
                .section-title {{ font-size: 14px; font-weight: bold; color: #0f172a; margin: 25px 0 15px 0; text-transform: uppercase; border-left: 4px solid #3b82f6; padding-left: 12px; }}
                .ai-summary {{ background: #f0f9ff; border-radius: 10px; padding: 20px; font-size: 12px; line-height: 1.6; color: #1e40af; margin-bottom: 20px; }}
                .footer {{ text-align: center; padding: 30px; color: #94a3b8; font-size: 10px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div style="font-size: 30px; font-weight: bold; letter-spacing: 2px; color: #3b82f6;">CARVIX AI</div>
                <div style="font-size: 13px; opacity: 0.8; margin-top: 8px;">PROFESYONEL DIJITAL EKSPERTIZ RAPORU</div>
            </div>
            <div class="container">
                <div class="info-bar">
                    <div class="info-item"><b>PLAKA:</b><br>{plate}</div>
                    <div class="info-item" style="text-align: center;"><b>ARAC TURU:</b><br>{clear_tr(config['label'])}</div>
                    <div class="info-item" style="text-align: right;"><b>RAPOR TARIHI:</b><br>{time.strftime('%d.%m.%Y %H:%M')}</div>
                </div>

                <div class="section-title">YAPAY ZEKA ANALIZ OZETI</div>
                <div class="ai-summary">{ai_comment}</div>

                <div style="text-align: center; margin: 30px 0;">
                    <img src="{config['base_img']}" style="width: 350px;">
                    <div style="font-size: 9px; color: #94a3b8; margin-top: 10px;">* Dijital Hasar Tespit Semasi</div>
                </div>

                <div class="section-title">DETAYLI EKSPERTIZ VE GORSEL KANITLAR</div>
                {cards_html}
            </div>
            <div class="footer">
                <b>YASAL UYARI:</b> Bu rapor Carvix AI tarafindan uretilmis bir on analizdir. Kesin sonuc icin TSE muayenesi onerilir.<br>
                <span style="color: #3b82f6;">www.carvix.site</span> | Rapor ID: {flow_token.upper()}
            </div>
        </body>
        </html>"""

        result_file = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_template), dest=result_file)
        return result_file.getvalue()
    except Exception as e:
        print(f"PDF Hatasi: {e}"); return None

# =========================================================
# MAİL FONKSİYONU
# =========================================================
def send_report_email(customer_email: str, flow_token: str, report_content: Any, vehicle_type: str = "Otomobil"):
    try:
        msg = MIMEMultipart()
        msg['From'] = f"Carvix AI <{SENDER_EMAIL}>"
        msg['To'] = customer_email
        msg['Subject'] = f"Ekspertiz Raporunuz Hazir - {vehicle_type}"
        
        body = f"Sayin Musterimiz,\n\nAraciniz icin yapilan yapay zeka destekli analiz tamamlanmistir. Detayli raporunuz ekteki PDF dosyasinda yer almaktadir.\n\nBizi tercih ettiginiz icin tesekkur ederiz.\n\nCarvix AI Ekibi"
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
        print(f"Mail Hatasi: {e}"); return False

# =========================================================
# APP & ENDPOINTS (EKSİKSİZ TAM LİSTE)
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
        return {"ok": False, "message": "Analiz verisi bos"}

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