"use client";

import { useEffect, useState } from "react";

export default function UploadPage({ params }: { params: { token: string } }) {
  const { token } = params;
  const api = process.env.NEXT_PUBLIC_API_BASE;

  const [status, setStatus] = useState("Analiz başlatılıyor...");
  const [dots, setDots] = useState("");

  /* =========================
     LOADING ANİMASYONU
     ========================= */
  useEffect(() => {
    const i = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "" : d + "."));
    }, 500);
    return () => clearInterval(i);
  }, []);

  /* =========================
     BACKEND STATUS POLL
     ========================= */
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${api}/session/${token}`);
        const data = await res.json();

        if (data.status === "analysis_completed") {
          setStatus("Analiz tamamlandı. Rapor hazırlanıyor...");
          clearInterval(interval);

          setTimeout(() => {
            window.location.href = `/report/${token}`;
          }, 1500);
        } else {
          setStatus("Analiz devam ediyor");
        }
      } catch {
        setStatus("Backend ile bağlantı kurulamadı");
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [api, token]);

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "#000",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        fontFamily: "Arial",
        textAlign: "center",
        padding: 24,
      }}
    >
      <div style={{ fontSize: 28, marginBottom: 16 }}>🔍</div>

      <h1 style={{ fontSize: 20, marginBottom: 12 }}>
        {status}
        {dots}
      </h1>

      <p style={{ fontSize: 14, opacity: 0.7, maxWidth: 320 }}>
        Video ve ses verileri yapay zekâ tarafından analiz ediliyor.
        Lütfen bu sayfayı kapatmayın.
      </p>
    </div>
  );
}
