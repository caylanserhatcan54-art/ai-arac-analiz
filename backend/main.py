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
    return ext if ext in [".jpg", ".jpeg", ".png", ".webp"] else ".bin"

def make_public_upload_url(filename: str):
    return f"{BASE_URL}/uploads/{filename}"

# =========================================================
# GÖRSELDEKİ PROMPT STİLİNDE PDF ÜRETME (YENİLENDİ)
# =========================================================
def create_pdf_report(flow_token: str, report_data: Any, vehicle_type: str = "Otomobil"):
    try:
        config = VEHICLE_CONFIGS.get(vehicle_type, VEHICLE_CONFIGS["Otomobil"])
        parts_analysis = report_data.get('parts_analysis', [])
        ai_comment = clear_tr(report_data.get('ai_comment', "Arac genel olarak iyi durumdadir."))
        plate = clear_tr(report_data.get('plate', '34 ABC 123'))
        
        table_rows_html = ""
        for p in parts_analysis:
            p_name = clear_tr(p['name']).replace("_", " ")
            status = clear_tr(p['status']).upper()
            note = clear_tr(p.get('note', '-'))
            img_url = p.get('image_url', '') 
            
            # Dinamik Durum Renkleri (Prompttaki gibi yeşil/sarı/kırmızı)
            if "ORIJINAL" in status or "TAMAM" in status:
                status_color = "#16a34a" # Yeşil
                label = "TAMAM"
            elif "GOZLEM" in status or "BOYALI" in status:
                status_color = "#ca8a04" # Sarı/Turuncu
                label = "KUSURLU"
            else:
                status_color = "#dc2626" # Kırmızı
                label = "KRITIK"

            table_rows_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-weight: bold; font-size: 10px;">{p_name}</td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: center;">
                    <span style="color: {status_color}; font-weight: bold; font-size: 10px;">{label}</span>
                </td>
                <td style="padding: 10px; border-bottom: 1px solid #e2e8f0; font-size: 9px; color: #475569;">{note}</td>
                <td style="padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;">
                    {f'<img src="{img_url}" style="width: 100px; height: 60px; border: 1px solid #cbd5e1; border-radius: 3px;">' if img_url else '<div style="font-size: 7px; color: #94a3b8;">Gorsel Yok</div>'}
                </td>
            </tr>"""

        html_template = f"""
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <style>
                @page {{ size: A4; margin: 1cm; }}
                body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; background-color: #ffffff; margin: 0; padding: 0; }}
                .header {{ text-align: center; border-bottom: 3px solid #1e293b; padding-bottom: 10px; margin-bottom: 20px; }}
                .header h1 {{ margin: 0; font-size: 24px; letter-spacing: 2px; }}
                .info-section {{ margin-bottom: 20px; }}
                .info-box {{ width: 100%; border: 1px solid #e2e8f0; border-collapse: collapse; }}
                .info-box td {{ padding: 8px; border: 1px solid #e2e8f0; font-size: 10px; }}
                .section-title {{ background: #f1f5f9; color: #1e293b; padding: 6px 10px; font-size: 11px; font-weight: bold; margin: 15px 0 10px 0; border-left: 4px solid #3b82f6; }}
                .diagram-container {{ text-align: center; margin: 20px 0; border: 1px dashed #cbd5e1; padding: 15px; border-radius: 8px; }}
                .ai-comment {{ padding: 10px; font-size: 10px; line-height: 1.5; color: #334155; background: #f8fafc; border: 1px solid #e2e8f0; }}
                .data-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                .data-table th {{ background: #1e293b; color: white; padding: 8px; text-align: left; font-size: 9px; }}
                .footer-table {{ width: 100%; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 10px; }}
                .signature {{ text-align: right; font-family: cursive; font-size: 14px; color: #64748b; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>EKSPERTIZ RAPORU</h1>
                <div style="font-size: 10px; color: #64748b;">{time.strftime('%d OCAK %Y')}</div>
            </div>

            <div class="info-section">
                <table class="info-box">
                    <tr>
                        <td width="20%"><b>ARAC BILGILERI</b></td>
                        <td width="30%">CARVIX AI ANALIZ</td>
                        <td width="20%"><b>PLAKA</b></td>
                        <td width="30%">{plate}</td>
                    </tr>
                    <tr>
                        <td><b>MARKA/MODEL</b></td>
                        <td>{clear_tr(config['label'])}</td>
                        <td><b>RAPOR NO</b></td>
                        <td>{flow_token[:8].upper()}</td>
                    </tr>
                </table>
            </div>

            <div class="section-title">KAPORTA - BOYA VE MEKANIK DURUMU</div>
            <div class="diagram-container">
                <img src="{config['base_img']}" style="width: 350px;">
                <div style="font-size: 8px; color: #94a3b8; margin-top: 8px;">* Renkli alanlar yapay zeka tarafindan tespit edilen islem gormus bolgeleri temsil eder.</div>
            </div>

            <div class="section-title">DETAYLI KONTROL LISTESI</div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th width="30%">PARCA ADI</th>
                        <th width="15%" style="text-align: center;">DURUM</th>
                        <th width="35%">ACIKLAMA</th>
                        <th width="20%" style="text-align: center;">GORSEL KANIT</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows_html}
                </tbody>
            </table>

            <div class="section-title">SONUC VE ONERILER</div>
            <div class="ai-comment">
                {ai_comment}
                <br><br>
                <b>Tahmini Onarim Maliyeti:</b> Yapay zeka tarafindan parca bazli analiz edilmektedir.
            </div>

            <table class="footer-table">
                <tr>
                    <td width="70%" style="font-size: 8px; color: #94a3b8;">
                        Bu rapor dijital olarak olusturulmustur. Kesin sonuc icin fiziki muayene onerilir.<br>
                        <b>CARVIX AI | www.carvix.site</b>
                    </td>
                    <td width="30%" class="signature">
                        <img src="https://www.carvix.site/logo.png" style="width: 40px;"><br>
                        Carvix Digital Sign
                    </td>
                </tr>
            </table>
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
        msg['Subject'] = f"Carvix AI Ekspertiz Raporunuz Hazir"
        
        body = f"Sayin Musterimiz,\n\nDijital ekspertiz raporunuz ekte sunulmustur.\n\nKeyifli surusler dileriz."
        msg.attach(MIMEText(body, 'plain'))

        pdf_data = create_pdf_report(flow_token, report_content, vehicle_type)
        if pdf_data:
            attachment = MIMEApplication(pdf_data, _subtype="pdf")
            attachment.add_header('Content-Disposition', 'attachment', filename=f"Carvix_Rapor_{flow_token[:8]}.pdf")
            msg.attach(attachment)

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Mail Hatasi: {e}"); return False

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