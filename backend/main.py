import os, json, uuid, time, requests, smtplib, io, re
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# PDF Kütüphanesi
from xhtml2pdf import pisa 

load_dotenv()

# =========================================================
# KARAKTER VE METİN TEMİZLEME
# =========================================================
def clear_tr(text):
    if not text: return ""
    tr_map = str.maketrans("İıŞşĞğÇçÖöÜü", "IiSsGgCcOoUu")
    return str(text).translate(tr_map)

# =========================================================
# ENV & AYARLAR
# =========================================================
BASE_URL = os.getenv("BASE_URL", "https://ai-arac-analiz-backend.onrender.com").rstrip("/")
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
# JSON YARDIMCILARI
# =========================================================
def _load_json(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except: return default

def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# =========================================================
# QWEN YORUMLU VE PLAKALI PDF RAPOR ÜRETİCİ
# =========================================================
def create_pdf_report(flow_token: str, report_data: Any, vehicle_type: str = "Otomobil"):
    try:
        config = VEHICLE_CONFIGS.get(vehicle_type, VEHICLE_CONFIGS["Otomobil"])
        parts_analysis = report_data.get('parts_analysis', [])
        # app.py'den gelen Qwen yorumunu ve plakayı çekiyoruz
        ai_comment = clear_tr(report_data.get('ai_comment', "Analiz verileri yapay zeka tarafından işlendi."))
        plate = clear_tr(report_data.get('plate', 'TESPIT EDILEMEDI'))
        
        table_rows_html = ""
        for p in parts_analysis:
            p_name = clear_tr(p['name']).replace("ANALIZ", "").replace("_", " ").strip()
            status = clear_tr(p['status']).upper()
            note = clear_tr(p.get('note', '-'))
            img_url = p.get('image_url', '') 
            
            # Durum Renkleri (Hassas Atama)
            status_color = "#16a34a" # Varsayılan Yeşil (TAMAM)
            if any(x in status for x in ["KUSURLU", "BOYALI", "HASARLI", "DEGISEN"]):
                status_color = "#ca8a04" # Sarı/Turuncu
            if "KRITIK" in status:
                status_color = "#dc2626" # Kırmızı

            table_rows_html += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; font-weight: bold; font-size: 10px;">{p_name}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; text-align: center;">
                    <div style="color: white; background-color: {status_color}; padding: 4px; border-radius: 4px; font-weight: bold; font-size: 9px;">{status}</div>
                </td>
                <td style="padding: 12px; border-bottom: 1px solid #e2e8f0; font-size: 9px; color: #475569;">{note}</td>
                <td style="padding: 5px; border-bottom: 1px solid #e2e8f0; text-align: center;">
                    <img src="{img_url}" style="width: 110px; height: 70px; border: 1px solid #cbd5e1; border-radius: 4px;">
                </td>
            </tr>"""

        html_template = f"""
        <html>
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
            <style>
                @page {{ size: A4; margin: 1cm; }}
                body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; }}
                .header {{ text-align: center; border-bottom: 3px solid #1e293b; padding-bottom: 10px; }}
                .info-box {{ width: 100%; border: 1px solid #e2e8f0; border-collapse: collapse; margin-top: 15px; }}
                .info-box td {{ padding: 10px; border: 1px solid #e2e8f0; font-size: 10px; }}
                .section-title {{ background: #f1f5f9; padding: 8px; font-size: 11px; font-weight: bold; margin-top: 20px; border-left: 5px solid #3b82f6; }}
                .ai-comment-box {{ padding: 15px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 10px; line-height: 1.6; margin-top: 10px; }}
                .data-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                .data-table th {{ background: #0f172a; color: white; padding: 10px; font-size: 9px; text-align: left; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1 style="margin:0;">CARVIX AI EKSPERTIZ RAPORU</h1>
                <div style="font-size: 10px; color: #64748b;">{time.strftime('%d.%m.%Y %H:%M')}</div>
            </div>

            <table class="info-box">
                <tr>
                    <td style="background:#f8fafc;"><b>ARAC TIPI</b></td><td>{clear_tr(config['label'])}</td>
                    <td style="background:#f8fafc;"><b>PLAKA</b></td><td><b>{plate}</b></td>
                </tr>
                <tr>
                    <td style="background:#f8fafc;"><b>RAPOR ID</b></td><td>#{flow_token[:8].upper()}</td>
                    <td style="background:#f8fafc;"><b>DURUM</b></td><td>DIJITAL ONAYLI</td>
                </tr>
            </table>

            <div class="section-title">ARAC SEMATIK GORUNUMU</div>
            <div style="text-align:center; padding: 20px;">
                <img src="{config['base_img']}" style="width: 350px;">
            </div>

            <div class="section-title">DETAYLI EKSPERTIZ LISTESI</div>
            <table class="data-table">
                <thead>
                    <tr><th>PARCA</th><th style="text-align:center;">DURUM</th><th>AI NOTU</th><th style="text-align:center;">KANIT GORSEL</th></tr>
                </thead>
                <tbody>{table_rows_html}</tbody>
            </table>

            <div class="section-title">USTA YORUMU (QWEN AI)</div>
            <div class="ai-comment-box">
                {ai_comment}
                <br><br>
                <i style="color:#94a3b8;">* Bu yorum yapay zeka tarafından teknik veriler analiz edilerek oluşturulmuştur.</i>
            </div>

            <div style="margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; text-align: center; font-size: 9px; color: #94a3b8;">
                Carvix AI Teknolojisi - www.carvix.site - Güvenli ve Hızlı Ekspertiz
            </div>
        </body>
        </html>"""

        result_file = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_template), dest=result_file)
        return result_file.getvalue()
    except Exception as e:
        print(f"PDF Hatasi: {e}"); return None

# =========================================================
# MAİL SERVİSİ
# =========================================================
def send_report_email(customer_email: str, flow_token: str, report_content: Any, vehicle_type: str):
    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication

        msg = MIMEMultipart()
        msg['From'] = f"Carvix AI <{SENDER_EMAIL}>"
        msg['To'] = customer_email
        msg['Subject'] = f"Carvix AI | Ekspertiz Raporunuz Hazir ({report_content.get('plate', 'Analiz')})"
        
        body = "Aracinizin yapay zeka destekli ekspertiz raporu tamamlanmistir. Detaylar ekteki PDF dosyasindadir."
        msg.attach(MIMEText(body, 'plain'))

        pdf_data = create_pdf_report(flow_token, report_content, vehicle_type)
        if pdf_data:
            attachment = MIMEApplication(pdf_data, _subtype="pdf")
            attachment.add_header('Content-Disposition', 'attachment', filename=f"Carvix_Rapor_{flow_token[:8]}.pdf")
            msg.attach(attachment)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Mail Hatasi: {e}"); return False

# =========================================================
# FASTAPI ENDPOINTS
# =========================================================
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

flows = _load_json(FLOWS_PATH, {})
jobs = _load_json(JOBS_PATH, {})

@app.post("/flows")
async def create_flow(payload: Dict[str, Any] = Body(default={})):
    token = str(uuid.uuid4())
    flows[token] = {
        "token": token, "vehicle_type": payload.get("vehicle_type", "Otomobil"), 
        "parts": {}, "status": "collecting", "report": None, "email": None
    }
    _save_json(FLOWS_PATH, flows)
    return {"token": token}

@app.post("/flows/{flow_token}/upload")
async def upload_images(flow_token: str, part_key: str = Form(...), files: List[UploadFile] = File(...)):
    flow = flows.get(flow_token)
    if not flow: raise HTTPException(404)
    if part_key not in flow["parts"]: flow["parts"][part_key] = []
    
    for f in files:
        stored_name = f"{uuid.uuid4()}{os.path.splitext(f.filename)[1]}"
        (UPLOAD_DIR / stored_name).write_bytes(await f.read())
        flow["parts"][part_key].append(f"{BASE_URL}/uploads/{stored_name}")
    
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
            return {"id": jid, "flow_token": j["flow_token"], "vehicle_type": flow.get("vehicle_type", "Otomobil"), "images": flow["parts"]}
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
    return flow

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)