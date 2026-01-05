"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

type Session = {
  token: string;
  scenario?: string | null;
  vehicle_type?: string | null;
  status: string;
};

const SCENARIOS = [
  { id: "buy_sell_seller", label: "Araç alım–satım (satıcıya yaptıracağım)" },
  { id: "buy_sell_buyer", label: "Araç alım–satım (kendim taratacağım)" },
  { id: "own_car", label: "Kendi aracım / eş–dost" },
  { id: "pre_inspection", label: "Muayene öncesi ön kontrol" },
];

const VEHICLES = [
  { id: "car", label: "Araba (içten yanmalı)" },
  { id: "electric_car", label: "Elektrikli araba" },
  { id: "motorcycle", label: "Motosiklet" },
  { id: "atv", label: "ATV" },
  { id: "pickup", label: "Pickup" },
  { id: "van", label: "Kamyonet / Minibüs" },
];

export default function FlowPage() {
  const params = useParams();
  const router = useRouter();
  const token = params?.token as string;

  const api = process.env.NEXT_PUBLIC_API_BASE;

  const [session, setSession] = useState<Session | null>(null);
  const [scenario, setScenario] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) return;

    fetch(`${api}/session/${token}`)
      .then((r) => r.json())
      .then((data) => {
        setSession(data);
        setScenario(data.scenario ?? "");
        setVehicle(data.vehicle_type ?? "");
      })
      .catch(() => setMsg("Session alınamadı. Backend çalışıyor mu?"));
  }, [token, api]);

  const save = async () => {
    if (!scenario || !vehicle) return;

    setMsg("Kaydediliyor...");

    const res = await fetch(`${api}/session/${token}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario,
        vehicle_type: vehicle,
        steps: [],
      }),
    });

    if (!res.ok) {
      setMsg("Kaydetme hatası.");
      return;
    }

    // ✅ ARAÇ TİPİ URL İLE TAŞINIYOR
    router.push(`/capture/${token}?vehicle=${vehicle}`);
  };

  if (!token) {
    return <div style={{ padding: 24 }}>Token bekleniyor…</div>;
  }

  return (
    <main style={{ padding: 20, maxWidth: 720, margin: "0 auto", fontFamily: "Arial" }}>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Carvix – Ön Analiz</h1>
      <p style={{ color: "#555", marginBottom: 20 }}>
        Lütfen analiz amacını ve araç tipini seçin.
      </p>

      {/* SENARYO */}
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 10 }}>1) Senaryo</h2>
        {SCENARIOS.map((s) => (
          <label
            key={s.id}
            style={{
              display: "block",
              padding: 12,
              marginBottom: 8,
              border: "1px solid #ccc",
              borderRadius: 8,
              background: scenario === s.id ? "#e6f0ff" : "#fff",
              cursor: "pointer",
            }}
          >
            <input
              type="radio"
              name="scenario"
              value={s.id}
              checked={scenario === s.id}
              onChange={(e) => setScenario(e.target.value)}
              style={{ marginRight: 8 }}
            />
            {s.label}
          </label>
        ))}
      </section>

      {/* ARAÇ */}
      <section style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, marginBottom: 10 }}>2) Araç tipi</h2>
        {VEHICLES.map((v) => (
          <label
            key={v.id}
            style={{
              display: "block",
              padding: 12,
              marginBottom: 8,
              border: "1px solid #ccc",
              borderRadius: 8,
              background: vehicle === v.id ? "#e6f0ff" : "#fff",
              cursor: "pointer",
            }}
          >
            <input
              type="radio"
              name="vehicle"
              value={v.id}
              checked={vehicle === v.id}
              onChange={(e) => setVehicle(e.target.value)}
              style={{ marginRight: 8 }}
            />
            {v.label}
          </label>
        ))}
      </section>

      <button
        onClick={save}
        disabled={!scenario || !vehicle}
        style={{
          width: "100%",
          padding: 16,
          fontSize: 18,
          borderRadius: 12,
          border: "none",
          background: !scenario || !vehicle ? "#ccc" : "#000",
          color: "#fff",
        }}
      >
        Devam Et → Kamera
      </button>

      {msg && <p style={{ marginTop: 12 }}>{msg}</p>}

      {session && (
        <p style={{ marginTop: 12, color: "#666" }}>
          Backend durum: <b>{session.status}</b>
        </p>
      )}
    </main>
  );
}
