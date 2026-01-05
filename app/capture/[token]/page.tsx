"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation"; // ✅ EKLENDİ

type Session = {
  token: string;
  scenario?: string | null;
  vehicle_type?: string | null;
  status: string;
};

const silhouetteMap: Record<string, string> = {
  car: "/silhouettes/car.png",
  electric_car: "/silhouettes/car.png",
  pickup: "/silhouettes/pickup.png",
  van: "/silhouettes/van.png",
  motorcycle: "/silhouettes/motorcycle.png",
  atv: "/silhouettes/atv.png",
};

const silhouetteScale: Record<string, number> = {
  car: 0.78,
  electric_car: 0.78,
  pickup: 0.82,
  van: 0.86,
  motorcycle: 0.55,
  atv: 0.6,
};

/* =============================
   🔥 VEHICLE TYPE NORMALIZE
============================== */
const normalizeVehicleType = (type?: string | null): string => {
  if (!type) return "car";
  const t = type.toLowerCase();

  if (["car", "sedan", "hatchback"].includes(t)) return "car";
  if (["electric_car", "electric", "ev"].includes(t)) return "electric_car";
  if (["motorcycle", "motor", "bike"].includes(t)) return "motorcycle";
  if (["atv", "quad"].includes(t)) return "atv";
  if (["pickup", "truck"].includes(t)) return "pickup";
  if (["van", "minivan", "kamyonet"].includes(t)) return "van";

  return "car";
};

export default function CapturePage() {
  const params = useParams();                // ✅ EKLENDİ
  const token = params?.token as string;     // ✅ DÜZELTİLDİ
  const api = process.env.NEXT_PUBLIC_API_BASE;

  const videoRef = useRef<HTMLVideoElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const liveIntervalRef = useRef<any>(null);

  const [vehicleType, setVehicleType] = useState("car");
  const [recording, setRecording] = useState(false);

  const [startTime, setStartTime] = useState<number | null>(null);
  const [rotation, setRotation] = useState(0);
  const [lastAlpha, setLastAlpha] = useState<number | null>(null);

  const [warnings, setWarnings] = useState<string[]>([]);
  const hasWarning = warnings.length > 0;

  const [msg, setMsg] = useState(
    "Aracın önünden başlayın ve rehber noktayı takip ederek etrafında dönün."
  );

  /* =============================
     SESSION → ARAÇ TİPİ
  ============================== */
  useEffect(() => {
    if (!token) return;

    fetch(`${api}/session/${token}`)
      .then((r) => r.json())
      .then((s: Session) => {
        const normalized = normalizeVehicleType(s.vehicle_type);
        setVehicleType(normalized);
      })
      .catch(() => {});
  }, [api, token]);

  /* =============================
     KAMERA
  ============================== */
  useEffect(() => {
  // ⛔ SERVER GUARD
  if (typeof window === "undefined") return;
  if (!navigator?.mediaDevices?.getUserMedia) {
    setMsg("Bu tarayıcı kamera erişimini desteklemiyor.");
    return;
  }

  let stream: MediaStream | null = null;

  navigator.mediaDevices
    .getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    })
    .then((s) => {
      stream = s;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play().catch(() => {});
      }
    })
    .catch(() => {
      setMsg("Kamera açılamadı. Tarayıcı izinlerini kontrol edin.");
    });

  return () => {
    stream?.getTracks().forEach((t) => t.stop());
  };
}, []);

  /* =============================
     GYRO – GERÇEK DÖNÜŞ
  ============================== */
  useEffect(() => {
    const handler = (e: DeviceOrientationEvent) => {
      if (!recording || e.alpha == null) return;

      if (lastAlpha !== null) {
        let diff = Math.abs(e.alpha - lastAlpha);
        if (diff > 180) diff = 360 - diff;
        setRotation((r) => Math.min(360, r + diff));
      }
      setLastAlpha(e.alpha);
    };

    window.addEventListener("deviceorientation", handler);
    return () => window.removeEventListener("deviceorientation", handler);
  }, [recording, lastAlpha]);

  /* =============================
     LIVE YOLO CHECK
  ============================== */
  const startLiveCheck = () => {
    if (liveIntervalRef.current) return;

    liveIntervalRef.current = setInterval(async () => {
      if (!videoRef.current || !canvasRef.current) return;

      const canvas = canvasRef.current;
      const video = videoRef.current;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, "image/jpeg", 0.7)
      );
      if (!blob) return;

      const form = new FormData();
      form.append("frame", blob);

      try {
        const res = await fetch(`${api}/live-check/${token}`, {
          method: "POST",
          body: form,
        });

        const data = await res.json();
        setWarnings(data.warnings || []);
      } catch {}
    }, 1000);
  };

  const stopLiveCheck = () => {
    if (liveIntervalRef.current) {
      clearInterval(liveIntervalRef.current);
      liveIntervalRef.current = null;
    }
    setWarnings([]);
  };

  /* =============================
     KAYDI BAŞLAT
  ============================== */
  const startRecording = () => {
    const stream = videoRef.current?.srcObject as MediaStream | null;
    if (!stream) {
      setMsg("Kamera hazır değil.");
      return;
    }

    chunks.current = [];
    setRotation(0);
    setLastAlpha(null);
    setStartTime(Date.now());

    const rec = new MediaRecorder(stream, {
      mimeType: "video/webm",
      videoBitsPerSecond: 4_000_000,
    });

    rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    rec.start();

    mediaRecorderRef.current = rec;
    setRecording(true);
    startLiveCheck();
    setMsg("Yavaşça yürüyün, aracı kadrajda tutun.");
  };

  /* =============================
     KAYDI BİTİR
  ============================== */
  const stopRecording = async () => {
    const duration =
      startTime ? (Date.now() - startTime) / 1000 : 0;

    if (duration < 20 || rotation < 300) {
      setMsg("360° tarama tamamlanmadı. Biraz daha yavaşça aracı dolaşın.");
      return;
    }

    stopLiveCheck();
    mediaRecorderRef.current?.stop();
    setRecording(false);
    setMsg("Video yükleniyor ve analiz ediliyor…");

    const blob = new Blob(chunks.current, { type: "video/webm" });
    const form = new FormData();
    form.append("video", blob);

    const res = await fetch(`${api}/upload/${token}/video`, {
      method: "POST",
      body: form,
    });

    if (res.ok) {
      window.location.href = `/report/${token}`;
    } else {
      setMsg("Yükleme hatası.");
    }
  };

  const silhouetteSrc = silhouetteMap[vehicleType];
  const scale = silhouetteScale[vehicleType] ?? 0.78;
  const progress = Math.min(100, Math.round((rotation / 360) * 100));

  /* =============================
     UI
  ============================== */
  return (
    <main style={{ margin: 0 }}>
      <div
        style={{
          position: "relative",
          height: "100vh",
          background: "#000",
          border: hasWarning ? "4px solid red" : "none",
        }}
      >
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />

        <canvas ref={canvasRef} style={{ display: "none" }} />

        <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
          <img
            src={silhouetteSrc}
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              transform: `translate(-50%, -50%) scale(${scale})`,
              width: "72vw",
              maxWidth: 520,
              opacity: 0.18,
            }}
          />

          <div
            style={{
              position: "absolute",
              left: "50%",
              top: "50%",
              width: "72vw",
              maxWidth: 520,
              aspectRatio: "1 / 1",
              transform: "translate(-50%, -50%)",
              borderRadius: "50%",
              border: "2px dashed rgba(255,255,255,.3)",
            }}
          />

          <div
            style={{
              position: "absolute",
              bottom: 120,
              left: "50%",
              transform: "translateX(-50%)",
              background: hasWarning
                ? "rgba(255,0,0,.75)"
                : "rgba(0,0,0,.6)",
              padding: "10px 14px",
              color: "#fff",
              borderRadius: 12,
              fontSize: 14,
              textAlign: "center",
            }}
          >
            {hasWarning
              ? "⚠️ Kadraj / mesafe uygun değil. Aracı merkeze alıp yaklaşın."
              : `${msg} • %${progress}`}
          </div>
        </div>

        <div
          style={{
            position: "absolute",
            bottom: 26,
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
          }}
        >
          {!recording ? (
            <button
              onClick={startRecording}
              style={{
                padding: "16px 26px",
                fontSize: 18,
                borderRadius: 999,
                background: "#00c853",
                color: "#fff",
                fontWeight: 900,
                border: "none",
              }}
            >
              ▶️ Çekimi Başlat
            </button>
          ) : (
            <button
              onClick={stopRecording}
              style={{
                padding: "16px 26px",
                fontSize: 18,
                borderRadius: 999,
                background: "#111",
                color: "#fff",
                fontWeight: 900,
                border: "none",
              }}
            >
              ⏹️ Bitir
            </button>
          )}
        </div>
      </div>
    </main>
  );
}
