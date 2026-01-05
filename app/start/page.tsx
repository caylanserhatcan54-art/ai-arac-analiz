"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function StartPage({ params }: { params: { token: string } }) {
  const router = useRouter();
  const [accepted, setAccepted] = useState(false);

  return (
    <div style={{ maxWidth: 800, margin: "40px auto", padding: 20 }}>
      <h1>Analize Başlamadan Önce</h1>

      <div style={{ background: "#f5f7fa", padding: 20, borderRadius: 10 }}>
        <ul>
          <li>Araç temiz olmalıdır (çamur, yoğun toz analiz doğruluğunu düşürür).</li>
          <li>Video gündüz ve iyi ışık koşullarında çekilmelidir.</li>
          <li>Gece, karanlık otopark veya yoğun yağmurda çekim önerilmez.</li>
          <li>Araç 360° yavaş ve sabit şekilde görüntülenmelidir.</li>
          <li>
            Motor sesi analizi için araç çalışır haldeyken kaput açık olmalı ve
            ses yakından kaydedilmelidir.
          </li>
        </ul>

        <p style={{ marginTop: 15, fontSize: 14, color: "#555" }}>
          Bu sistem bir ekspertiz hizmeti değildir. Yapay zekâ; video ve ses
          kayıtlarından <b>olasılık ve risk değerlendirmesi</b> yapar.
        </p>
      </div>

      <label style={{ display: "block", marginTop: 20 }}>
        <input
          type="checkbox"
          checked={accepted}
          onChange={(e) => setAccepted(e.target.checked)}
        />{" "}
        Yukarıdaki bilgilendirmeyi okudum ve anladım
      </label>

      <button
        disabled={!accepted}
        onClick={() => router.push(`/capture/${params.token}`)}
        style={{
          marginTop: 20,
          padding: "12px 24px",
          fontSize: 16,
          cursor: accepted ? "pointer" : "not-allowed",
          background: accepted ? "#2563eb" : "#999",
          color: "#fff",
          border: "none",
          borderRadius: 6,
        }}
      >
        Analize Başla
      </button>
    </div>
  );
}
