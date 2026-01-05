"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const VEHICLES = [
  { key: "car", label: "🚗 Otomobil" },
  { key: "electric_car", label: "🔋 Elektrikli Araç" },
  { key: "motorcycle", label: "🏍️ Motosiklet" },
  { key: "atv", label: "🛻 ATV" },
  { key: "pickup", label: "🚙 Pickup" },
  { key: "van", label: "🚐 Kamyonet / Van" },
];

export default function VehicleSelectPage({ params }: any) {
  const { token } = params;
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  async function selectVehicle(type: string) {
    if (loading) return;

    setSelected(type);
    setLoading(true);

    // Mevcut session bilgisini al
    const sessionRes = await fetch(`http://127.0.0.1:8000/session/${token}`);
    const session = await sessionRes.json();

    // Güncelle
    await fetch(`http://127.0.0.1:8000/session/${token}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario: session.scenario,
        vehicle_type: type,
        steps: session.steps || [],
      }),
    });

    router.push(`/capture/${token}`);
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        padding: 24,
        background: "#0f172a",
        color: "white",
        fontFamily: "Arial",
      }}
    >
      <h1 style={{ fontSize: 24, marginBottom: 12 }}>
        Araç Tipini Seç
      </h1>

      <p style={{ opacity: 0.8, marginBottom: 24 }}>
        Hangi tür aracı analiz edeceğimizi seçin.
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr",
          gap: 12,
        }}
      >
        {VEHICLES.map((v) => (
          <button
            key={v.key}
            onClick={() => selectVehicle(v.key)}
            disabled={loading}
            style={{
              padding: "18px 20px",
              fontSize: 18,
              borderRadius: 14,
              border: selected === v.key ? "2px solid #22c55e" : "1px solid #334155",
              background: selected === v.key ? "#052e16" : "#020617",
              color: "white",
              textAlign: "left",
            }}
          >
            {v.label}
          </button>
        ))}
      </div>

      {loading && (
        <p style={{ marginTop: 20, opacity: 0.7 }}>
          Yönlendiriliyor…
        </p>
      )}
    </main>
  );
}
