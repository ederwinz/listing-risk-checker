"use client";

import type { ResultSlot } from "@/types/report";
import { RiskBadge } from "./RiskBadge";
import { RiskReport } from "./RiskReport";

export function ReportCard({ slot }: { slot: ResultSlot }) {
  const r = slot.report;
  const title = r
    ? [r.extracted.claimed_brand, r.extracted.claimed_productline].filter(Boolean).join(" ") ||
      slot.file.name
    : slot.file.name;
  const sub = r
    ? [r.extracted.seller_name, r.extracted.platform].filter(Boolean).join(" · ")
    : "Listing screenshot";

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      {/* header */}
      <div className="rcard">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="pic" src={slot.previewUrl} alt={slot.file.name} />
        <div className="meta">
          {slot.status === "loading" || slot.status === "pending" ? (
            <>
              <div className="shimmer" style={{ width: "62%", height: 13, marginBottom: 8 }} />
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="spin" />
                <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
                  {slot.status === "pending" ? "Queued…" : "Matching records…"}
                </span>
              </div>
            </>
          ) : slot.status === "error" ? (
            <>
              <div className="brand">Couldn’t check this listing</div>
              <div className="sub" style={{ color: "var(--high)" }}>
                {slot.error}
              </div>
            </>
          ) : r ? (
            <>
              <div className="brand">{title}</div>
              <div className="sub">{sub}</div>
              <div style={{ marginTop: 7 }}>
                <RiskBadge level={r.risk_level} />
              </div>
            </>
          ) : null}
        </div>
      </div>

      {/* report body */}
      {slot.status === "done" && r && (
        <div style={{ padding: "4px 16px 16px" }}>
          <RiskReport report={r} />
        </div>
      )}
    </div>
  );
}
