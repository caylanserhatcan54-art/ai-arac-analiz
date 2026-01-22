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
# KARAKTER TEMIZLEME FONKSIYONU
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
# GÖRSEL DESTEKLİ MODERN PDF ÜRETME (REVIZE EDILDI)
# =========================================================
def create_pdf_report(flow_token: str, report_data: Any, vehicle_type: str = "Otomobil"):
    try:
        config = VEHICLE_CONFIGS.get(vehicle_type, VEHICLE_CONFIGS["Otomobil"])
        parts_analysis = report_data.get('parts_analysis', [])
        ai_comment = clear_tr(report_data.get('ai_comment', "Analiz verileri islendi."))
        plate = clear_tr(report_data.get('plate', 'BELIRLENEMEDI'))
        
        # TABLO SATIRLARI OLUŞTURMA
        table_rows_html = ""
        for p in parts_analysis:
            p_name = clear_tr(p['name'])
            status = clear_tr(p['status']).upper()
            note = clear_tr(p.get('note', '-'))
            img_url = p.get('image_url', '') 
            
            # Duruma göre renk seçimi
            status_style = "background: #dc2626; color: white;" if "KRITIK" in status else "background: #f59e0b; color: white;"
            if "ORIJINAL" in status: status_style = "background: #16a34a; color: white;"

            table_rows_html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #334155; font-weight: bold; font-size: 11px;">{p_name}</td>
                <td style="padding: 10px; border: 1px solid #334155; text-align: center;">
                    <span style="padding: 4px 8px; border-radius: 4px; font-size: 9px; {status_style}">{status}</span>
                </td>
                <td style="padding: 10px; border: 1px solid #334155; font-size: 10px;">{note}</td>
                <td style="padding: 5px; border: 1px solid #334155; text-align: center;">
                    {f'<img src="{img_url}" style="width: 120px; height: 70px; border-radius: 4px; object-fit: cover;">' if img_url else '<div style="font-size: 8px; color: #64748b;">Gorsel Kanit Yok</div>'}
                </td>
            </tr>"""

        html_template = f"""
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <style>
                @page {{ size: A4; margin: 0; }}
                body {{ font-family: Helvetica, Arial, sans-serif; background-color: #0f172a; margin: 0; padding: 0; color: #f8fafc; }}
                .main-container {{ width: 92%; margin: 20px auto; background-color: #1e293b; border-radius: 10px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }}
                .header-box {{ border-bottom: 2px solid #3b82f6; padding-bottom: 15px; margin-bottom: 20px; }}
                .brand {{ font-size: 28px; font-weight: bold; color: #3b82f6; }}
                .sub-brand {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; }}
                .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; background: #334155; border-radius: 5px; }}
                .info-table td {{ padding: 12px; border: 1px solid #475569; font-size: 11px; color: #f1f5f9; }}
                .section-title {{ background: #3b82f6; color: white; padding: 8px 15px; font-size: 13px; font-weight: bold; border-radius: 4px; margin: 20px 0 10px 0; }}
                .ai-box {{ background: #0f172a; border-left: 4px solid #3b82f6; padding: 15px; font-size: 11px; line-height: 1.6; color: #cbd5e1; font-style: italic; }}
                .data-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background: #1e293b; }}
                .data-table th {{ background: #334155; color: #94a3b8; padding: 10px; text-align: left; font-size: 10px; border: 1px solid #334155; }}
                .footer {{ text-align: center; margin-top: 30px; font-size: 9px; color: #64748b; }}
            </style>
        </head>
        <body>
            <div class="main-container">
                <div class="header-box">
                    <table width="100%">
                        <tr>
                            <td><span class="brand">CARVIX AI</span><br><span class="sub-brand">Profesyonel Dijital Ekspertiz</span></td>
                            <td style="text-align: right; color: #3b82f6; font-size: 18px; font-weight: bold;">RAPOR NO: {flow_token[:8].upper()}</td>
                        </tr>
                    </table>
                </div>

                <table class="info-table">
                    <tr>
                        <td width="33%"><b>PLAKA:</b> {plate}</td>
                        <td width="33%"><b>ARAC TIPI:</b> {clear_tr(config['label'])}</td>
                        <td width="33%"><b>TARIH:</b> {time.strftime('%d.%m.%Y %H:%M')}</td>
                    </tr>
                </table>

                <div class="section-title">EKSPERTIZ OZETI VE UZMAN YORUMU</div>
                <div class="ai-box">
                    {ai_comment}
                </div>

                <div style="text-align: center; margin: 25px 0; background: #0f172a; padding: 20px; border-radius: 10px;">
                    <img src="{config['base_img']}" style="width: 380px;">
                    <div style="font-size: 9px; color: #475569; margin-top: 10px;">* Yukaridaki sematik gosterim yapay zeka tarafindan analiz edilen bolgeleri temsil eder.</div>
                </div>

                <div class="section-title">DETAYLI PARCA ANALIZI VE TESPITLER</div>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th width="25%">KONTROL NOKTASI</th>
                            <th width="15%" style="text-align: center;">DURUM</th>
                            <th width="35%">TESPIT NOTLARI</th>
                            <th width="25%" style="text-align: center;">GORSEL ISPAT</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows_html}
                    </tbody>
                </table>

                <div class="footer">
                    <b>YASAL BILGILENDIRME:</b> Bu rapor Carvix AI tarafindan uretilmis bir on analiz raporudur. 
                    Verilen bilgiler fiziki muayene yerine gecmez. Kesin sonuc icin yetkili servis onayi onerilir.<br>
                    <span style="color: #3b82f6;">www.carvix.site</span>
                </div>
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
        msg['Subject'] = f"Carvix AI Ekspertiz Raporunuz Hazir - {vehicle_type}"
        
        body = f"Sayin Musterimiz,\n\nAraciniz icin hazirlanan dijital ekspertiz raporu ektedir.\n\nGuvenli surusler dileriz.\n\nCarvix AI Ekibi"
        msg.attach(MIMEText(body, 'plain'))

        pdf_data = create_pdf_report(flow_token, report_content, vehicle_type)
        if pdf_data:
            attachment = MIMEApplication(pdf_data, _subtype="pdf")
            attachment.add_header('Content-Disposition', 'attachment', filename=f"Ekspertiz_Raporu_{flow_token[:8]}.pdf")
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