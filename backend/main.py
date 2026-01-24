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

# Shopier Bilgileri
SHOPIER_USER = "82e968ed5fc8210544588fc8cfd2000d"
SHOPIER_PASS = "29583cd4b9b67ef31c71ec8ef16e8641"

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
        ai_comment = clear_tr(report_data.get('ai_comment', "Analiz verileri yapay zeka tarafından işlendi."))
        plate = clear_tr(report_data.get('plate', 'TESPIT EDILEMEDI'))
        
        table_rows_html = ""
        for p in parts_analysis:
            p_name = clear_tr(p['name']).replace("ANALIZ", "").replace("_", " ").strip()
            status = clear_tr(p['status']).upper()
            note = clear_tr(p.get('note', '-'))
            img_url = p.get('image_url', '') 
            
            status_color = "#16a34a" 
            if any(x in status for x in ["KUSURLU", "BOYALI", "HASARLI", "DEGISEN"]):
                status_color = "#ca8a04" 
            if "KRITIK" in status:
                status_color = "#dc2626" 

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

        html_template = f"""<html>...Rapor İçeriği...{table_rows_html}</html>""" # (Şablonun geri kalanı aynı)

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
        "parts": {}, "status": "collecting", "report": None, "email": None, "paid": False
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
    # Önemli Değişiklik: İşi jobs'a eklemiyoruz, beklemeye alıyoruz.
    flow["status"] = "waiting_payment"
    _save_json(FLOWS_PATH, flows)
    return {"ok": True, "message": "Payment required"}

# SHOPİER OSB CALLBACK
@app.post("/shopier-callback")
async def shopier_callback(request: Request):
    try:
        form_data = await request.form()
        data = dict(form_data)
        print(f"DEBUG: Shopier'den Gelen Tum Veri: {data}") # Loglarda bunu göreceğiz
        
        flow_token = data.get("platform_order_id")
        print(f"DEBUG: Ayiklanan Flow Token: {flow_token}")

        if flow_token and flow_token in flows:
            # ... (kuyruğa alma kodları aynı kalsın)
            return Response(content="success", status_code=200)
        else:
            print(f"HATA: Token bulunamadi! Gelen: {flow_token}, Mevcut Tokenlar: {list(flows.keys())}")
            return Response(content="fail", status_code=400)
            
    except Exception as e:
        print(f"Callback Hatasi: {e}")
        return Response(content="error", status_code=500)

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