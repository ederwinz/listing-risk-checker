"use client";

import { useEffect, useRef, useState } from "react";
import type { Report, ResultSlot, RiskLevel } from "@/types/report";
import { ReportCard } from "./ReportCard";
import { PlusIcon } from "./icons";

interface ResultsListProps {
  files: File[];
  onReset: () => void;
}

export function ResultsList({ files, onReset }: ResultsListProps) {
  const [slots, setSlots] = useState<ResultSlot[]>(() =>
    files.map((file) => ({
      id: `${file.name}-${file.lastModified}`,
      file,
      previewUrl: URL.createObjectURL(file),
      status: "pending",
    })),
  );

  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    slots.forEach((slot) => {
      setSlots((prev) => prev.map((s) => (s.id === slot.id ? { ...s, status: "loading" } : s)));

      const formData = new FormData();
      formData.append("image", slot.file);

      fetch("/api/analyze", { method: "POST", body: formData })
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok) throw new Error(data.error ?? "Unknown error");
          return data as Report;
        })
        .then((report) => {
          setSlots((prev) =>
            prev.map((s) => (s.id === slot.id ? { ...s, status: "done", report } : s)),
          );
        })
        .catch((err) => {
          setSlots((prev) =>
            prev.map((s) => (s.id === slot.id ? { ...s, status: "error", error: err.message } : s)),
          );
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const doneCount = slots.filter((s) => s.status === "done" || s.status === "error").length;
  const allDone = doneCount === slots.length;

  const tally = (level: RiskLevel) =>
    slots.filter((s) => s.status === "done" && s.report?.risk_level === level).length;

  return (
    <div className="stack" style={{ gap: 10 }}>
      {/* progress while running */}
      {!allDone && (
        <div className="progress" style={{ marginBottom: 8 }}>
          <i style={{ width: `${(doneCount / slots.length) * 100}%` }} />
        </div>
      )}

      {/* tally once finished */}
      {allDone && (
        <div className="tally" style={{ marginBottom: 6 }}>
          <div className="t low">
            <div className="n">{tally("low")}</div>
            <div className="k">Match</div>
          </div>
          <div className="t medium">
            <div className="n">{tally("medium")}</div>
            <div className="k">Partial</div>
          </div>
          <div className="t high">
            <div className="n">{tally("high")}</div>
            <div className="k">No match</div>
          </div>
        </div>
      )}

      {slots.map((slot) => (
        <ReportCard key={slot.id} slot={slot} />
      ))}

      <button className="btn btn-ghost" style={{ marginTop: 6 }} onClick={onReset}>
        <PlusIcon /> Check more listings
      </button>
    </div>
  );
}
