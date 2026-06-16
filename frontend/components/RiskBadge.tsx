"use client";

import type { RiskLevel } from "@/types/report";
import { useDict } from "./dict-context";

export function RiskBadge({ level }: { level: RiskLevel }) {
  const t = useDict();
  return (
    <span className={`badge ${level}`}>
      <span className="dot" />
      {t.badge[level]}
    </span>
  );
}
