import type { RiskLevel } from "@/types/report";

const STROKE: Record<RiskLevel, string> = {
  low: "var(--low)",
  medium: "var(--med)",
  high: "var(--high)",
  unverifiable: "var(--gray)",
};

export function ConfidenceRing({
  pct,
  level,
  size = 46,
}: {
  pct: number;
  level: RiskLevel;
  size?: number;
}) {
  const r = (size - 7) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth="5" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={STROKE[level]}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - pct / 100)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="52%"
        dominantBaseline="middle"
        textAnchor="middle"
        fontFamily="var(--font-mono)"
        fontSize="12"
        fontWeight="600"
        fill="var(--ink)"
      >
        {pct}
      </text>
    </svg>
  );
}
