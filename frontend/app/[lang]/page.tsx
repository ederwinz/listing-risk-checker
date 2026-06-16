"use client";

import { use, useState } from "react";
import { getDict } from "@/app/dictionaries";
import { DictProvider } from "@/components/dict-context";
import { UploadButton } from "@/components/UploadButton";
import { ResultsList } from "@/components/ResultsList";
import { BrandMark } from "@/components/BrandMark";
import { RiskBadge } from "@/components/RiskBadge";
import { ShieldIcon, ChevLeftIcon } from "@/components/icons";

export default function Home({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = use(params);
  const t = getDict(lang);
  const otherLang = lang === "en" ? "zh" : "en";

  const [files, setFiles] = useState<File[] | null>(null);

  // ── Results view ──────────────────────────────────────────────
  if (files) {
    return (
      <DictProvider value={t}>
        <main className="cp-app">
          <div className="cp-pad">
            <div className="topbar">
              <button className="iconbtn" onClick={() => setFiles(null)} aria-label={t.backAria}>
                <ChevLeftIcon style={{ color: "var(--muted)" }} />
              </button>
              <BrandMark />
              <div style={{ width: 38 }} />
            </div>

            <h1 className="h2" style={{ marginBottom: 4 }}>
              {t.resultsTitle}
            </h1>
            <p className="lede" style={{ fontSize: 13.5, marginBottom: 16 }}>
              {t.resultsSub(files.length)}
            </p>

            <ResultsList files={files} onReset={() => setFiles(null)} />
          </div>
        </main>
      </DictProvider>
    );
  }

  // ── Home / landing ────────────────────────────────────────────
  return (
    <DictProvider value={t}>
      <main className="cp-app">
        <div className="cp-pad">
          <div className="topbar">
            <BrandMark />
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <a className="langtoggle" href={`/${otherLang}`}>
                {otherLang === "zh" ? "中文" : "EN"}
              </a>
              <button className="iconbtn" aria-label={t.aboutAria}>
                <ShieldIcon style={{ color: "var(--muted)" }} />
              </button>
            </div>
          </div>

          <div className="eyebrow" style={{ marginBottom: 14 }}>
            {t.eyebrow}
          </div>
          <h1 className="display" style={{ marginBottom: 14 }}>
            {t.headline[0]}
            <br />
            {t.headline[1]}
          </h1>
          <p className="lede" style={{ marginBottom: 22, maxWidth: "30ch" }}>
            {t.lede}
          </p>

          {/* sample verdict peek */}
          <div className="card" style={{ padding: 14, marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div className="peek-pic" />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>Owala FreeSip</div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>{t.peekSize}</div>
              </div>
              <RiskBadge level="low" />
            </div>
          </div>
          <div
            className="label"
            style={{ textTransform: "none", letterSpacing: ".02em", color: "var(--faint)", paddingLeft: 4 }}
          >
            {t.statLine}
          </div>

          <div className="spacer" />

          <UploadButton onFiles={setFiles} />

          <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 16 }}>
            <span className="chip">Owala</span>
            <span className="chip">Rhode</span>
            <span className="chip">Gymshark</span>
            <span className="chip">+11</span>
          </div>
          <p className="note" style={{ marginTop: 16, textAlign: "center" }}>
            {t.homeNote}
          </p>
        </div>
      </main>
    </DictProvider>
  );
}
