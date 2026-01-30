import os, json, uuid, time, requests, smtplib, io, re, base64
from typing import List, Optional, Dict, Any
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from xhtml2pdf import pisa 

load_dotenv()

# =========================================================
# AYARLAR VE ARAÇ ŞEMALARI
# =========================================================
BASE_URL = os.getenv("BASE_URL", "https://ai-arac-analiz-backend.onrender.com").rstrip("/")

MAIL_POOL = [
    {"email": "carvix.site@gmail.com", "pass": "bfgrqaquupmyifcy"},
    {"email": "carvixrapor@gmail.com", "pass": "uoduqgunxdickfxr"},
    {"email": "raporcarvix@gmail.com", "pass": "dqdjjfkadhuvcsix"},
    {"email": "sitecarvix@gmail.com", "pass": "bnazyzrkxobqhjkp"}
]
current_mail_index = 0

DATA_DIR = Path("./data")
UPLOAD_DIR = Path("./uploads")
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FLOWS_PATH = DATA_DIR / "flows.json"
JOBS_PATH = DATA_DIR / "jobs.json"

VEHICLE_CONFIGS = {
    "Otomobil": {"schema": "https://www.carvix.site/car-base.png", "label": "Binek Arac"},
    "Motosiklet": {"schema": "https://www.carvix.site/moto-base.png", "label": "Motosiklet"},
    "Pickup": {"schema": "https://www.carvix.site/pickup-base.png", "label": "Pickup / Kamyonet"},
    "Van": {"schema": "https://www.carvix.site/van-base.png", "label": "Ticari Arac (Panelvan/Kamyon)"},
    "ATV": {"schema": "https://www.carvix.site/atv-base.png", "label": "ATV / Arazi Araci"},
    "Elektrikli": {"schema": "https://www.carvix.site/car-base.png", "label": "Elektrikli Arac"}
}

# =========================================================
# YARDIMCI FONKSIYONLAR
# =========================================================
def clear_tr(text):
    if not text: return ""
    tr_map = str.maketrans("İıŞşĞğÇçÖöÜü", "IiSsGgCcOoUu")
    return str(text).translate(tr_map)

def _load_json(path: Path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except: return default

def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# =========================================================
# PDF ÜRETİCİ (DÜZELTİLMİŞ)
# =========================================================
def create_pdf_report(flow_token: str, report_data: Any, vehicle_type: str = "Otomobil"):
    try:
        config = VEHICLE_CONFIGS.get(vehicle_type, VEHICLE_CONFIGS["Otomobil"])
        parts_analysis = report_data.get('parts_analysis', [])
        rejected_images = report_data.get('rejected_images', [])
        ai_confidence = report_data.get('ai_confidence', 0)
        
        raw_comment = report_data.get('ai_comment', "Teknik analiz yapildi.")
        ai_comment = clear_tr(raw_comment).replace("Yapay zeka analizime gore", "Yapilan teknik inceleme sonucunda;")
        ai_comment = ai_comment.replace("Selam,", "").replace("Merhaba,", "").strip()

        plate = clear_tr(report_data.get('plate', 'TESPIT EDILEMEDI'))
        report_id = f"#{flow_token[:8].upper()}"
        date_str = time.strftime("%d.%m.%Y %H:%M")

        # Parça Analiz Satırları
        table_rows_html = ""
        for p in parts_analysis:
            p_name = clear_tr(p.get('name','')).replace("ANALIZ", "").replace("_", " ").strip()
            p_status = clear_tr(p.get('status','')).strip().upper()
            note = clear_tr(p.get('note', '-'))
            img_url = p.get('image_url', '')

            # Duruma göre renk belirleme
            if p_status in ["KUSURLU", "BOYALI", "HASARLI", "DEGISEN", "EZIK", "CIZIK"]:
                status_color = "#ca8a04"  # turuncu
            elif p_status in ["KRITIK", "MACUN", "ISLEMLI"]:
                status_color = "#dc2626"  # kırmızı
            elif p_status in ["ORJINAL", "ORIGINAL"]:
                status_color = "#16a34a"  # yeşil
            else:
                status_color = "#64748b"  # gri - bilinmeyen
                p_status = "BİLGİ YOK"

            table_rows_html += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #eee; font-size: 10px; font-weight: bold;">{p_name}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">
                    <div style="color: white; background-color: {status_color}; padding: 4px; border-radius: 4px; font-size: 8px; font-weight: bold;">{p_status}</div>
                </td>
                <td style="padding: 10px; border-bottom: 1px solid #eee; font-size: 9px; color: #444;">{note}</td>
                <td style="padding: 5px; border-bottom: 1px solid #eee; text-align: center;">
                    <img src="{img_url}" style="width: 100px; height: 60px; border-radius: 4px; border: 1px solid #ddd;">
                </td>
            </tr>"""

        # Reddedilen Görseller Listesi
        rejected_html = ""
        if rejected_images:
            rejected_html = '<div class="section-title" style="background:#fff1f2; color:#be123c; border-left-color:#be123c;"> ANALIZE UYGUN GORULMEYEN GORSELLER</div><ul>'
            for r in rejected_images:
                rejected_html += f'<li style="font-size:9px; color:#be123c; margin-bottom:3px;"><b>{clear_tr(r.get("part",""))}:</b> {clear_tr(r.get("reason",""))}</li>'
            rejected_html += '</ul>'

        html_template = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; padding: 0; margin: 0; }}
                .header {{ text-align: center; background-color: #0f172a; color: white; padding: 20px; }}
                .info-box {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                .info-box td {{ border: 1px solid #e2e8f0; padding: 10px; font-size: 10px; background: #f8fafc; }}
                .section-title {{ background: #eff6ff; color: #1d4ed8; padding: 8px; font-weight: bold; border-left: 5px solid #1d4ed8; margin-top: 20px; font-size: 11px; }}
                .schema-div {{ text-align: center; padding: 20px; background: white; }}
                .comment-box {{ background: #fdfdfd; border: 1px solid #cbd5e1; padding: 15px; font-size: 10px; line-height: 1.6; color: #334155; border-radius: 6px; font-style: italic; }}
                .footer {{ text-align: center; font-size: 9px; color: #64748b; margin-top: 40px; border-top: 1px solid #eee; padding-top: 10px; }}
                .confidence-badge {{ display: inline-block; background: #22c55e; color: white; padding: 2px 6px; border-radius: 10px; font-size: 9px; margin-left: 10px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1 style="margin:0; font-size: 22px;">CARVIX AI EKSPERTIZ RAPORU</h1>
                <p style="margin: 5px 0 0 0; font-size: 10px; opacity: 0.8;">Yapay Zeka ve Optik Analiz Teknolojisi</p>
            </div>
            <table class="info-box">
                <tr><td><b>PLAKA:</b> {plate}</td><td><b>TARIH:</b> {date_str}</td></tr>
                <tr><td><b>RAPOR ID:</b> {report_id}</td><td><b>ANALIZ GUVENI:</b> <span class="confidence-badge">%{ai_confidence}</span></td></tr>
            </table>
            <div class="section-title">TEKNIK HASAR SEMASI ({config['label']})</div>
            <div class="schema-div"><img src="{config['schema']}" style="width: 320px;"></div>
            
            <div class="section-title">DETAYLI EKSPERTIZ ANALIZI</div>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background: #334155; color: white;">
                        <th style="padding: 10px; font-size: 10px; text-align: left;">PARCA</th>
                        <th style="padding: 10px; font-size: 10px;">DURUM</th>
                        <th style="padding: 10px; font-size: 10px; text-align: left;">USTA ANALIZ NOTU</th>
                        <th style="padding: 10px; font-size: 10px;">GORSEL KANIT</th>
                    </tr>
                </thead>
                <tbody>{table_rows_html}</tbody>
            </table>

            {rejected_html}

            <div class="section-title">USTA OZET YORUMU</div>
            <div class="comment-box">{ai_comment}</div>
            <div class="footer">www.carvix.site</div>
        </body>
        </html>
        """

        result_file = io.BytesIO()
        pisa_status = pisa.CreatePDF(src=html_template, dest=result_file)
        if pisa_status.err:
            print("PDF oluşturulurken hata oluştu:", pisa_status.err)
            return None
        return result_file.getvalue()

    except Exception as e:
        print(f"PDF Hatasi: {e}")
        return None

# =========================================================
# MAIL SERVISI
# =========================================================
def send_report_email(customer_email: str, flow_token: str, report_content: Any, vehicle_type: str):
    global current_mail_index
    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication

        acc = MAIL_POOL[current_mail_index]
        current_mail_index = (current_mail_index + 1) % len(MAIL_POOL)

        msg = MIMEMultipart()
        msg['From'] = f"Carvix AI <{acc['email']}>"
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
            server.login(acc["email"], acc["pass"])
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Mail Hatasi ({acc['email']}): {e}")
        return False

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
    flow["status"] = "waiting_payment"
    _save_json(FLOWS_PATH, flows)
    return {"ok": True}

@app.post("/shopier-callback")
async def shopier_callback(request: Request):
    try:
        form_data = await request.form()
        data = dict(form_data)
        res_encoded = data.get("res")
        if not res_encoded: return Response(content="fail", status_code=400)
        res_decoded = base64.b64decode(res_encoded).decode('utf-8')
        shopier_data = json.loads(res_decoded)
        s_email = shopier_data.get("email")
        s_platform_id = shopier_data.get("platform_order_id")
        target_token = None
        if s_platform_id in flows:
            target_token = s_platform_id
        else:
            for token, f in reversed(list(flows.items())):
                if f.get("email") == s_email and f.get("status") == "waiting_payment":
                    target_token = token
                    break
        if target_token:
            job_id = str(uuid.uuid4())
            jobs[job_id] = {"id": job_id, "flow_token": target_token, "status": "queued"}
            flows[target_token].update({"status": "queued", "paid": True})
            _save_json(JOBS_PATH, jobs)
            _save_json(FLOWS_PATH, flows)
            return Response(content="success", status_code=200)
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
    j.update({"status": "done", "result": payload})
    flow = flows.get(j["flow_token"])
    if flow:
        flow.update({"status": "done", "report": payload})
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
