"use client";

import type { Report, RiskLevel } from "@/types/report";
import { FieldRow, type FieldStatus } from "./FieldRow";
import { ConfidenceRing } from "./ConfidenceRing";
import { useDict } from "./dict-context";
import { CheckIcon, WarnIcon, CrossIcon, DashIcon, ExtIcon } from "./icons";

const VERDICT_ICON: Record<RiskLevel, React.ReactNode> = {
  low: <CheckIcon />,
  medium: <WarnIcon />,
  high: <CrossIcon />,
  unverifiable: <DashIcon />,
};

export function RiskReport({ report }: { report: Report }) {
  const t = useDict();
  const {
    extracted,
    match_type,
    match_context,
    discrepancies,
    expected_matchid,
    official_screenshot_url,
    official_source_url,
    risk_level,
  } = report;

  const sizeIssue = discrepancies.find((d) => d.field === "size");

  // ── Brand row ───────────────────────────────────────────────
  const brandStatus: FieldStatus = match_type === "BRAND_NOT_FOUND" ? "fail" : "ok";
  const brandResult =
    match_type === "BRAND_NOT_FOUND"
      ? t.brandNotInDb
      : match_context.brand_count
        ? t.brandInDb(match_context.brand_count)
        : t.brandConfirmed;
  const brandDetail =
    match_type === "BRAND_NOT_FOUND" && match_context.known_brands
      ? t.knownBrands(match_context.known_brands.slice(0, 8).join(", "))
      : undefined;

  // ── Product line row ────────────────────────────────────────
  const plSkip = match_type === "BRAND_NOT_FOUND";
  const plStatus: FieldStatus = plSkip
    ? "skip"
    : match_type === "PRODUCT_LINE_NOT_FOUND"
      ? "fail"
      : "ok";
  const plResult = plSkip
    ? t.notProvided
    : match_type === "PRODUCT_LINE_NOT_FOUND"
      ? t.plNotRecognized
      : t.plRecognized;
  const plDetail =
    match_type === "PRODUCT_LINE_NOT_FOUND" && match_context.known_product_lines
      ? t.knownLines(match_context.known_product_lines.slice(0, 8).join(", "))
      : undefined;

  // ── Colorway row ────────────────────────────────────────────
  const cwSkip = match_type === "BRAND_NOT_FOUND" || match_type === "PRODUCT_LINE_NOT_FOUND";
  const cwStatus: FieldStatus = cwSkip
    ? "skip"
    : match_type === "EXACT"
      ? "ok"
      : match_type === "FUZZY_COLORWAY"
        ? "warn"
        : "fail";
  const cwResult = cwSkip
    ? match_type === "PRODUCT_LINE_NOT_FOUND"
      ? t.cwNotProvidedNoLine
      : t.notProvided
    : match_type === "EXACT"
      ? t.cwExact
      : match_type === "FUZZY_COLORWAY"
        ? t.cwFuzzy(
            match_context.closest_colorway ?? "",
            Math.round((match_context.best_fuzzy_score ?? 0) * 100),
          )
        : t.cwNotFound;
  const cwDetail =
    !cwSkip && match_type !== "EXACT" && match_context.known_colorways?.length
      ? t.knownColorways(match_context.known_colorways.join(", "))
      : undefined;

  // ── Size row ────────────────────────────────────────────────
  const sizeSkip = cwSkip || !expected_matchid;
  const sizeStatus: FieldStatus = sizeSkip
    ? "skip"
    : sizeIssue
      ? "fail"
      : extracted.claimed_size
        ? "ok"
        : "skip";
  const sizeResult = sizeSkip
    ? t.notProvided
    : sizeIssue
      ? sizeIssue.message
          .split("officially offered sizes")
          .pop()
          ?.trim()
          .replace(/^\(|\)$/g, "") ?? t.sizeMismatch
      : extracted.claimed_size
        ? t.sizeOfficiallyOffered
        : "";

  // ── Verdict summary line ────────────────────────────────────
  const statuses: FieldStatus[] = [brandStatus, plStatus, cwStatus, sizeStatus];
  const checked = statuses.filter((s) => s !== "skip").length;
  const issues = statuses.filter((s) => s === "fail" || s === "warn").length;
  const verdictSub =
    risk_level === "low"
      ? t.verdictSubLow
      : risk_level === "unverifiable"
        ? t.verdictSubUnverifiable
        : t.verdictSubIssues(issues, checked);

  const pct = Math.round((report.overall_score ?? 0) * 100);

  return (
    <div className="stack" style={{ gap: 0 }}>
      {/* verdict banner */}
      <div className={`verdict ${risk_level}`}>
        <div className="row">
          <span className="ico">{VERDICT_ICON[risk_level]}</span>
          <div style={{ flex: 1 }}>
            <div className="vtitle">{t.verdictTitle[risk_level]}</div>
            <div className="vsub">{verdictSub}</div>
          </div>
          <ConfidenceRing pct={pct} level={risk_level} />
        </div>
      </div>

      {/* breakdown */}
      <div className="label" style={{ margin: "18px 2px 9px" }}>
        {t.detailCheck}
      </div>
      <div className="fields">
        <FieldRow status={brandStatus} label={t.fieldBrand} claimed={extracted.claimed_brand} result={brandResult} detail={brandDetail} />
        <FieldRow status={plStatus} label={t.fieldProductLine} claimed={extracted.claimed_productline} result={plResult} detail={plDetail} />
        <FieldRow status={cwStatus} label={t.fieldColorway} claimed={extracted.claimed_colorway} result={cwResult} detail={cwDetail} />
        <FieldRow status={sizeStatus} label={t.fieldSize} claimed={extracted.claimed_size} result={sizeResult} />
      </div>

      {/* official reference */}
      {official_screenshot_url?.startsWith("https://") ? (
        <>
          <div className="label" style={{ margin: "18px 2px 9px" }}>
            {t.officialReference}
          </div>
          <div className="card" style={{ padding: 13 }}>
            <div className="ref">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="pic" src={official_screenshot_url} alt="Official product" />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13.5 }}>
                  {expected_matchid ? t.matchedRecord : t.closestRecord}
                </div>
                {expected_matchid ? (
                  <div className="mono" style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>
                    {expected_matchid}
                  </div>
                ) : (
                  <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>
                    {t.noExactRecord}
                  </div>
                )}
                {official_source_url && (
                  <a
                    className="link"
                    style={{ marginTop: 8 }}
                    href={official_source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {t.viewOnOfficial} <ExtIcon />
                  </a>
                )}
              </div>
            </div>
          </div>
        </>
      ) : null}

      <p className="note" style={{ margin: "16px 6px 0" }}>
        {t.reportNote}
      </p>
    </div>
  );
}
