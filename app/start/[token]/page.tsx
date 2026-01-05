"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const SCENARIOS = [
  {
    key: "buy_sell",
    title: "🚗 Araç Alım – Satım",
    desc: "Aracı satın almadan önce veya satıcıya kontrol yaptırmak için",
  },
  {
    key: "self_check",
    title: "🧍‍♂️ Kendi Aracım / Eş-Dost",
    desc: "Merak ettiğiniz aracın genel durumunu görmek için",
  },
  {
    key: "pre_inspection",
    title: "🛠️ Muayene Öncesi",
    desc: "Muayeneye girmeden önce olası riskleri görmek için",
  },
];

export default function StartPage({ params }: any) {
  const { token } = params;
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function selectScenario(scenarioKey: string) {
    setLoading(true);

    // Şimdilik araç tipini varsayılan car bırakıyoruz
    await fetch(`http://127.0.0.1:8000/session/${token}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario: scenarioKey,
        vehicle_type: "car",
        steps: [], // capture sayfasında set edilecek
      }),
    });

    router.push(`/vehicle/${token}`);
  }

  return (
    <main style={{ padding: 20, maxWidth: 600, margin: "0 auto" }}>
      <h1 style={{ fontSize: 26, marginBottom: 10 }}>
        Analiz Amacını Seç
      </h1>
      <p style={{ marginBottom: 20, color: "#555" }}>
        Bu seçim rapor dilini ve değerlendirme şeklini etkiler.
      </p>

      {SCENARIOS.map((s) => (
        <button
          key={s.key}
          disabled={loading}
          onClick={() => selectScenario(s.key)}
          style={{
            width: "100%",
            padding: 16,
            marginBottom: 12,
            textAlign: "left",
            borderRadius: 12,
            border: "1px solid #ddd",
            background: "white",
          }}
        >
          <strong style={{ fontSize: 18 }}>{s.title}</strong>
          <div style={{ fontSize: 14, color: "#666", marginTop: 4 }}>
            {s.desc}
          </div>
        </button>
      ))}
    </main>
  );
}
