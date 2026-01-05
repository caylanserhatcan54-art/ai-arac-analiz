from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Image,
)
from reportlab.lib.units import cm


# =========================
# BRAND COLORS
# =========================
PRIMARY = HexColor("#0f172a")
ACCENT = HexColor("#00c853")
WARNING = HexColor("#b45309")
GRAY = HexColor("#475569")


# =========================
# STYLES
# =========================
def _styles():
    base = getSampleStyleSheet()

    base.add(
        ParagraphStyle(
            name="TitleCarvix",
            fontSize=22,
            leading=26,
            textColor=PRIMARY,
            alignment=TA_CENTER,
            spaceAfter=18,
        )
    )

    base.add(
        ParagraphStyle(
            name="SectionTitle",
            fontSize=14,
            leading=18,
            textColor=PRIMARY,
            spaceBefore=18,
            spaceAfter=8,
            fontName="Helvetica-Bold",
        )
    )

    base.add(
        ParagraphStyle(
            name="NormalText",
            fontSize=10.5,
            leading=14,
            textColor=GRAY,
        )
    )

    base.add(
        ParagraphStyle(
            name="StrongText",
            fontSize=11,
            leading=14,
            textColor=PRIMARY,
            fontName="Helvetica-Bold",
        )
    )

    base.add(
        ParagraphStyle(
            name="WarningText",
            fontSize=10,
            leading=14,
            textColor=WARNING,
        )
    )

    base.add(
        ParagraphStyle(
            name="Footer",
            fontSize=9,
            leading=12,
            textColor=GRAY,
            alignment=TA_CENTER,
        )
    )

    return base


# =========================
# HELPERS
# =========================
def _kv_table(data: Dict[str, str]) -> Table:
    rows = []
    for k, v in data.items():
        rows.append([f"<b>{k}</b>", v])

    table = Table(
        rows,
        colWidths=[6 * cm, 10 * cm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e5e7eb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _severity_text(level: str) -> str:
    level = (level or "").lower()
    if level == "high":
        return "YÜKSEK RİSK"
    if level == "medium":
        return "ORTA RİSK"
    if level == "low":
        return "DÜŞÜK RİSK"
    return "BİLİNMİYOR"


# =========================
# MAIN PDF GENERATOR
# =========================
def generate_pdf_report(
    *,
    output_path: str,
    session: Dict[str, Any],
    video_quality: Dict[str, Any],
    coverage: Dict[str, Any],
    damage: Dict[str, Any],
    engine_audio: Optional[Dict[str, Any]],
    confidence: Dict[str, Any],
    ai_commentary: Dict[str, Any],
) -> str:
    """
    Generates professional CARVIX PDF report.
    Returns output_path.
    """

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    styles = _styles()
    story: List[Any] = []

    # =========================
    # HEADER
    # =========================
    story.append(Paragraph("CARVIX – AI Araç Ön Analiz Raporu", styles["TitleCarvix"]))
    story.append(
        Paragraph(
            "Uzaktan ön bilgilendirme raporu (ekspertiz yerine geçmez)",
            styles["NormalText"],
        )
    )
    story.append(Spacer(1, 12))

    # =========================
    # SESSION INFO
    # =========================
    story.append(Paragraph("Rapor Bilgileri", styles["SectionTitle"]))

    story.append(
        _kv_table(
            {
                "Rapor Kodu": session.get("token", "-"),
                "Araç Tipi": session.get("vehicle_type", "-"),
                "Senaryo": session.get("scenario", "-"),
                "Rapor Tarihi": datetime.now().strftime("%d.%m.%Y %H:%M"),
            }
        )
    )

    # =========================
    # CONFIDENCE
    # =========================
    story.append(Paragraph("Rapor Güven Skoru", styles["SectionTitle"]))
    story.append(
        Paragraph(
            f"<b>{confidence.get('confidence_score', 0)}/100</b> – "
            f"{confidence.get('confidence_level', '').upper()} güven",
            styles["StrongText"],
        )
    )

    for r in confidence.get("reasons", []):
        story.append(Paragraph(f"• {r}", styles["NormalText"]))

    # =========================
    # VIDEO QUALITY
    # =========================
    story.append(Paragraph("Video Çekim Kalitesi", styles["SectionTitle"]))
    story.append(
        _kv_table(
            {
                "Süre (sn)": f"{video_quality.get('duration_sec', 0):.1f}",
                "Çözünürlük": f"{video_quality.get('width')} x {video_quality.get('height')}",
                "FPS": str(video_quality.get("fps", "-")),
                "Kalite Durumu": "UYGUN" if video_quality.get("ok") else "SINIRLI",
            }
        )
    )

    for h in video_quality.get("hints", []):
        story.append(Paragraph(f"• {h}", styles["WarningText"]))

    # =========================
    # COVERAGE
    # =========================
    story.append(Paragraph("Görsel Kapsama Analizi", styles["SectionTitle"]))
    story.append(
        Paragraph(
            f"Kapsama Oranı: <b>%{int((coverage.get('coverage_ratio', 0) or 0) * 100)}</b>",
            styles["NormalText"],
        )
    )

    # =========================
    # DAMAGE
    # =========================
    story.append(Paragraph("Görsel Hasar Risk Analizi", styles["SectionTitle"]))
    story.append(
        Paragraph(
            f"Genel Risk Seviyesi: <b>{_severity_text(damage.get('summary', {}).get('severity'))}</b>",
            styles["StrongText"],
        )
    )

    # =========================
    # 🔍 SUSPICIOUS VISUALS – 2×2 GRID
    # =========================
    suspicious = session.get("suspicious_images") or []
    if suspicious:
        story.append(PageBreak())
        story.append(Paragraph("Şüpheli Görsel Bulgular", styles["SectionTitle"]))
        story.append(
            Paragraph(
                "Aşağıdaki görseller, yüklenen video içerisinden alınmış örnek karelerdir. "
                "Kesin hasar veya parça değişimi anlamına gelmez.",
                styles["NormalText"],
            )
        )
        story.append(Spacer(1, 12))

        grid_rows = []
        row = []

        for item in suspicious:
            img_path = item.get("image_path")
            if not img_path or not os.path.exists(img_path):
                continue

            cell = [
                Image(img_path, width=7 * cm, height=5 * cm),
                Paragraph(
                    item.get("caption", "Görsel risk sinyali"),
                    styles["NormalText"],
                ),
            ]

            row.append(cell)

            if len(row) == 2:
                grid_rows.append(row)
                row = []

        if row:
            grid_rows.append(row)

        table = Table(grid_rows, colWidths=[8 * cm, 8 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(table)

    # =========================
    # AI COMMENTARY
    # =========================
    story.append(PageBreak())
    story.append(Paragraph("Yapay Zekâ Değerlendirmesi", styles["SectionTitle"]))
    story.append(
        Paragraph(
            ai_commentary.get("text", "").replace("\n", "<br/>"),
            styles["NormalText"],
        )
    )

    # =========================
    # LEGAL
    # =========================
    story.append(Spacer(1, 18))
    story.append(
        Paragraph(
            "⚠️ <b>Yasal Uyarı</b><br/>"
            "Bu rapor, kullanıcı tarafından yüklenen video ve ses kayıtları üzerinden "
            "yapay zekâ destekli ön analiz amacıyla oluşturulmuştur. "
            "Kesin teşhis niteliği taşımaz ve <b>ekspertiz yerine geçmez</b>. "
            "Satın alma veya teknik kararlar öncesinde yetkili servis veya profesyonel "
            "ekspertiz kuruluşlarına başvurulması önerilir.",
            styles["WarningText"],
        )
    )

    # =========================
    # FOOTER
    # =========================
    story.append(Spacer(1, 24))
    story.append(
        Paragraph(
            "CARVIX © 2026 – Uzaktan AI Destekli Araç Ön Analiz Sistemi",
            styles["Footer"],
        )
    )

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    doc.build(story)

    return output_path
