"use client";

import { CheckIcon, WarnIcon, CrossIcon, DashIcon } from "./icons";
import { useDict } from "./dict-context";

export type FieldStatus = "ok" | "warn" | "fail" | "skip";

const ICONS: Record<FieldStatus, React.ReactNode> = {
  ok: <CheckIcon />,
  warn: <WarnIcon />,
  fail: <CrossIcon />,
  skip: <DashIcon />,
};

interface FieldRowProps {
  status: FieldStatus;
  label: string;
  claimed: string;
  result: string;
  detail?: string;
}

export function FieldRow({ status, label, claimed, result, detail }: FieldRowProps) {
  const t = useDict();
  return (
    <div className="field">
      <span className={`fico ${status}`}>{ICONS[status]}</span>
      <div className="fbody">
        <div className="label">{label}</div>
        <div className="fval">
          {claimed || <span className="none">{t.notInListing}</span>}
        </div>
        {result && <div className={`fresult ${status}`}>{result}</div>}
        {detail && <div className="fdetail">{detail}</div>}
      </div>
    </div>
  );
}
