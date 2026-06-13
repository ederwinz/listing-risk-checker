import type { RiskLevel } from "@/types/report";

const LABELS: Record<RiskLevel, string> = {
  low: "Match confirmed",
  medium: "Partial match",
  high: "No match found",
  unverifiable: "Unverifiable",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className={`badge ${level}`}>
      <span className="dot" />
      {LABELS[level]}
    </span>
  );
}
