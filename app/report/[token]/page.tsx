"use client";

import { useEffect, useState } from "react";

type Session = {
  token: string;
  scenario: string;
  vehicle_type: string;
  status: string;

  ai_confidence?: {
    score: number;
    label: string;
    explanation: string;
    warnings?: string[];
    confidence_level?: string;
  };

  ai_commentary?: {
    final_text: string;
    risk: string;
    disclaimer?: string;
  };

  damage_results?: Record<string, any>;
  engine_audio?: any;
};

function prettyVehicle(v: string) {
  const map: Record<string, string> = {
    car: "Araba (içten yanmalı)",
    electric_car: "Elektrikli araba",
    motorcycle: "Motosiklet",
    atv: "ATV",
    pickup: "Pickup",
    van: "Van / Kamyonet / Minibüs",
  };
  return map[v] || v;
}

function prettyScenario(s: string) {
  const map: Record<string, string> = {
    buy_sell_seller: "Araç alım–satım (satıcı çekimi)",
    buy_sell_buyer: "Araç alım–satım (alıcı çekimi)",
    own_car: "Kendi aracım / eş–dost",
    pre_inspection: "Muayene öncesi ön kontrol",
    buy_sell: "Araç alım–satım",
  };
  return map[s] || s;
}

function prettyWarning(w: string) {
  const map: Record<string, string> = {
    visible_damage_detected: "Görsel hasar sinyali tespit edildi",
    paint_or_panel_intervention_risk: "Boya / parça müdahalesi şüphesi",
    engine_audio_low_quality: "Motor sesi kaydı düşük kaliteli",
    insufficient_360_coverage: "360° araç çevresi yeterince kapsanmadı",
    limited_capture_steps: "Çekim adımları sınırlı",
  };
  return map[w] || w;
}

export default function ReportPage({ params }: { params: { token: string } }) {
  const token = params.token;
  const api = process.env.NEXT_PUBLIC_API_BASE;

  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${api}/session/${token}`)
      .then((r) => r.json())
      .then((data) => {
        setSession(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [token, api]);

  if (loading) return <div className="container" style={{ padding: 24 }}>Rapor hazırlanıyor…</div>;
  if (!session) return <div className="container" style={{ padding: 24 }}>Rapor bulunamadı.</div>;

  const scorePct = session.ai_confidence ? Math.round(session.ai_confidence.score * 100) : null;

  return (
    <div>
      <div className="nav">
        <div className="container nav-inner">
          <div className="brand">
            <span className="brand-badge" />
            Carvix
          </div>
          <div className="nav-links">
            <a href="/">Ana Sayfa</a>
            <a href="/#nasil">Nasıl çalışır?</a>
            <a href={`/report/${token}.pdf`} target="_blank" rel="noreferrer">
              PDF
            </a>
          </div>
        </div>
      </div>

      <section className="section">
        <div className="container">
          <div className="card" style={{ padding: 22, maxWidth: 920, margin: "0 auto" }}>

            {/* --- ÜST BİLGİ --- */}
            {/* (senin kodun aynen korunuyor) */}

            {/* RİSK SKORU */}
            {session.ai_confidence && (
              <>
                <div className="hr" />

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  <div className="card" style={{ padding: 16 }}>
                    <div className="kicker">Genel Risk Değerlendirmesi</div>
                    <div style={{ fontWeight: 900, fontSize: 22, marginTop: 6 }}>
                      %{scorePct} – {session.ai_confidence.label}
                    </div>
                    <p className="p" style={{ marginTop: 10, lineHeight: 1.65 }}>
                      {session.ai_confidence.explanation}
                    </p>
                  </div>

                  <div className="card" style={{ padding: 16 }}>
                    <div className="kicker">Özet</div>
                    <p className="p" style={{ marginTop: 10 }}>
                      Bu skor; çekim kalitesi, açı ve ışığa bağlı olarak değişebilir.
                      Nihai karar öncesi profesyonel kontrol önerilir.
                    </p>
                  </div>
                </div>

                {/* 🔴 YENİ: UYARI LİSTESİ */}
                {session.ai_confidence.warnings && session.ai_confidence.warnings.length > 0 && (
                  <div
                    className="card"
                    style={{
                      marginTop: 14,
                      padding: 14,
                      background: "#fef2f2",
                      borderLeft: "6px solid #ef4444",
                    }}
                  >
                    <div style={{ fontWeight: 900, marginBottom: 6 }}>
                      ⚠️ Analizi Etkileyen Faktörler
                    </div>
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {session.ai_confidence.warnings.map((w) => (
                        <li key={w} style={{ fontSize: 14 }}>
                          {prettyWarning(w)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}

            {/* AI YORUMU */}
            {session.ai_commentary && (
              <>
                <div className="hr" />
                <div>
                  <div className="kicker">Yapay Zekâ Genel Değerlendirmesi</div>

                  <div
                    className="card"
                    style={{
                      padding: 16,
                      marginTop: 10,
                      borderLeft: "6px solid #0f172a",
                    }}
                  >
                    <p style={{ margin: 0, lineHeight: 1.75, fontWeight: 650 }}>
                      {session.ai_commentary.final_text}
                    </p>

                    {session.ai_commentary.disclaimer && (
                      <p
                        style={{
                          marginTop: 12,
                          fontSize: 13,
                          color: "#475569",
                          fontStyle: "italic",
                        }}
                      >
                        {session.ai_commentary.disclaimer}
                      </p>
                    )}

                    <div style={{ marginTop: 10, fontWeight: 800 }}>
                      Genel Risk Seviyesi: {session.ai_commentary.risk}
                    </div>
                  </div>
                </div>
              </>
            )}

          </div>
        </div>
      </section>
    </div>
  );
}
