"use client";

import { useState } from "react";
import { UploadButton } from "@/components/UploadButton";
import { ResultsList } from "@/components/ResultsList";
import { BrandMark } from "@/components/BrandMark";
import { RiskBadge } from "@/components/RiskBadge";
import { ShieldIcon, ChevLeftIcon } from "@/components/icons";

export default function Home() {
  const [files, setFiles] = useState<File[] | null>(null);

  // ── Results view ──────────────────────────────────────────────
  if (files) {
    return (
      <main className="cp-app">
        <div className="cp-pad">
          <div className="topbar">
            <button className="iconbtn" onClick={() => setFiles(null)} aria-label="Back">
              <ChevLeftIcon style={{ color: "var(--muted)" }} />
            </button>
            <BrandMark />
            <div style={{ width: 38 }} />
          </div>

          <h1 className="h2" style={{ marginBottom: 4 }}>
            Results
          </h1>
          <p className="lede" style={{ fontSize: 13.5, marginBottom: 16 }}>
            {files.length} listing{files.length !== 1 ? "s" : ""} · checked against official
            records
          </p>

          <ResultsList files={files} onReset={() => setFiles(null)} />
        </div>
      </main>
    );
  }

  // ── Home / landing ────────────────────────────────────────────
  return (
    <main className="cp-app">
      <div className="cp-pad">
        <div className="topbar">
          <BrandMark />
          <button className="iconbtn" aria-label="About">
            <ShieldIcon style={{ color: "var(--muted)" }} />
          </button>
        </div>

        <div className="eyebrow" style={{ marginBottom: 14 }}>
          Reference mismatch checker
        </div>
        <h1 className="display" style={{ marginBottom: 14 }}>
          Know what&rsquo;s
          <br />
          official.
        </h1>
        <p className="lede" style={{ marginBottom: 22, maxWidth: "30ch" }}>
          Screenshot a listing from Rednote, Taobao or Xianyu. We check every detail against the
          brand&rsquo;s own records.
        </p>

        {/* sample verdict peek */}
        <div className="card" style={{ padding: 14, marginBottom: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div className="peek-pic" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>Owala FreeSip</div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>Sunny Daze · 945 ml</div>
            </div>
            <RiskBadge level="low" />
          </div>
        </div>
        <div
          className="label"
          style={{ textTransform: "none", letterSpacing: ".02em", color: "var(--faint)", paddingLeft: 4 }}
        >
          checked in 1.4s against 10,142 records
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
          Reports mismatch risk only — never a verdict on authenticity.
        </p>
      </div>
    </main>
  );
}
