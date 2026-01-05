"use client";

export default function HomePage() {
  return (
    <div>
      {/* NAVBAR */}
      <div className="nav">
        <div className="container nav-inner">
          <div className="brand">
            <span className="brand-badge" />
            Carvix
          </div>

          <div className="nav-links">
            <a href="#nedir">Nedir?</a>
            <a href="#nasil">Nasıl çalışır?</a>
            <a href="#guvence">Güvence</a>
            <button
              className="btn btn-primary"
              onClick={() => (window.location.href = "/payment")}
            >
              Rapor Oluştur →
            </button>
          </div>
        </div>
      </div>

      {/* HERO */}
      <section className="hero">
        <div className="container">
          <div className="hero-grid">
            <div className="card hero-panel">
              <div className="hero-visual" />
              <div style={{ position: "relative" }}>
                <div className="badge">🔍 Video + 🔊 Ses • AI Ön Analiz</div>
                <div className="h1">
                  Aracı satın almadan önce
                  <br />
                  yapay zekâya sorun.
                </div>
                <p className="p" style={{ maxWidth: 560 }}>
                  Carvix, telefonla çekilen video ve (gerekiyorsa) motor sesinden
                  olası riskleri özetler; görsel kanıtlarla PDF rapor üretir.
                </p>

                <div style={{ display: "flex", gap: 12, marginTop: 18, flexWrap: "wrap" }}>
                  <button
                    className="btn btn-primary"
                    onClick={() => (window.location.href = "/payment")}
                  >
                    Hemen Ön Analiz Al →
                  </button>
                  <button
                    className="btn btn-ghost"
                    onClick={() => {
                      const el = document.getElementById("nasil");
                      el?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    Nasıl çalışır?
                  </button>
                </div>

                <p className="p" style={{ marginTop: 14, fontSize: 13, color: "#64748b" }}>
                  * Ekspertiz değildir. Ön analiz ve bilgilendirme amaçlıdır.
                </p>
              </div>
            </div>

            {/* RIGHT PANEL */}
            <div className="card hero-right">
              <div>
                <div className="kicker">Ne alacaksın?</div>
                <div style={{ fontWeight: 900, fontSize: 20, letterSpacing: "-0.02em", marginTop: 6 }}>
                  Premium PDF + AI Değerlendirme
                </div>
                <p className="p" style={{ marginTop: 10 }}>
                  Hasar bulguları, risk skoru, motor sesi özeti (uygunsa) ve
                  “insansı” tek paragraf AI yorumu.
                </p>

                <div className="hr" />

                <div className="kicker">Kapsam</div>
                <div style={{ display: "grid", gap: 8, marginTop: 10, color: "#334155", fontWeight: 700 }}>
                  <div>• Araba (içten yanmalı)</div>
                  <div>• Elektrikli araba (ses analizi yok)</div>
                  <div>• Motosiklet / ATV</div>
                  <div>• Pickup / Van</div>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
                <div>
                  <div className="kicker">Tek seferlik</div>
                  <div style={{ fontSize: 22, fontWeight: 900 }}>129,90 TL</div>
                </div>
                <button className="btn btn-primary" onClick={() => (window.location.href = "/payment")}>
                  Başla →
                </button>
              </div>
            </div>
          </div>

          {/* STEPS */}
          <div id="nasil" className="step-row">
            <div className="step">
              <b>1) Ödeme & Akış</b>
              <div className="p">Tek seferlik ödeme sonrası senaryo ve araç tipini seçersin.</div>
            </div>
            <div className="step">
              <b>2) Kamera yönlendirme</b>
              <div className="p">Adım adım çekim talimatlarıyla video kaydı alınır.</div>
            </div>
            <div className="step">
              <b>3) Analiz & Rapor</b>
              <div className="p">Hasar + (uygunsa) motor sesi analizi yapılır, PDF hazır olur.</div>
            </div>
          </div>
        </div>
      </section>

      {/* NEDIR */}
      <section id="nedir" className="section">
        <div className="container">
          <div className="kicker">Nedir Carvix?</div>
          <div style={{ fontSize: 28, fontWeight: 900, letterSpacing: "-0.03em", marginTop: 6 }}>
            Video ve ses verisiyle “ön risk” görünürlüğü.
          </div>
          <p className="p" style={{ marginTop: 10, maxWidth: 860 }}>
            Carvix, ekspertiz yerine geçmez; ancak aracı görmeden önce
            “gözden kaçabilecek riskleri” hızlıca işaretler ve net bir rapora dönüştürür.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginTop: 18 }}>
            <div className="card" style={{ padding: 18 }}>
              <div className="kicker">Görsel Kanıt</div>
              <div style={{ fontWeight: 900, fontSize: 18, marginTop: 6 }}>Hasar tespiti</div>
              <p className="p" style={{ marginTop: 8 }}>Bulgular ve kanıt görselleri PDF’e eklenir.</p>
            </div>
            <div className="card" style={{ padding: 18 }}>
              <div className="kicker">Ses Analizi</div>
              <div style={{ fontWeight: 900, fontSize: 18, marginTop: 6 }}>Motor sesi</div>
              <p className="p" style={{ marginTop: 8 }}>Uygun araçlarda ses verisiyle risk özeti.</p>
            </div>
            <div className="card" style={{ padding: 18 }}>
              <div className="kicker">AI Yorum</div>
              <div style={{ fontWeight: 900, fontSize: 18, marginTop: 6 }}>İnsansı özet</div>
              <p className="p" style={{ marginTop: 8 }}>Her raporda araç türüne göre farklı, doğal anlatım.</p>
            </div>
          </div>

          <div className="hr" />

          <div id="guvence" className="card" style={{ padding: 18 }}>
            <div className="kicker">Güvence</div>
            <div style={{ fontWeight: 900, fontSize: 18, marginTop: 6 }}>Şeffaflık</div>
            <p className="p" style={{ marginTop: 8 }}>
              Rapor; çekim kalitesi, açı ve ışığa bağlıdır. Nihai karar öncesi profesyonel kontrol önerilir.
            </p>
          </div>

          <div style={{ marginTop: 18 }}>
            <button className="btn btn-primary" onClick={() => (window.location.href = "/payment")}>
              Rapor Oluştur →
            </button>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer style={{ padding: "22px 0 34px", color: "#64748b" }}>
        <div className="container" style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ fontWeight: 800 }}>Carvix</div>
          <div style={{ fontSize: 13 }}>
            © {new Date().getFullYear()} Carvix • Ön analiz ve bilgilendirme amaçlıdır.
          </div>
        </div>
      </footer>
    </div>
  );
}
