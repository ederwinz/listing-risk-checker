import type { Report, RiskLevel } from "@/types/report";
import { FieldRow, type FieldStatus } from "./FieldRow";
import { ConfidenceRing } from "./ConfidenceRing";
import { CheckIcon, WarnIcon, CrossIcon, DashIcon, ExtIcon } from "./icons";

const VERDICT_TITLE: Record<RiskLevel, string> = {
  low: "Matches official records",
  medium: "Partial match — review details",
  high: "No official match found",
  unverifiable: "Couldn’t verify this listing",
};
const VERDICT_ICON: Record<RiskLevel, React.ReactNode> = {
  low: <CheckIcon />,
  medium: <WarnIcon />,
  high: <CrossIcon />,
  unverifiable: <DashIcon />,
};

export function RiskReport({ report }: { report: Report }) {
  const {
    extracted,
    match_type,
    match_context,
    discrepancies,
    expected_matchid,
    expected_matchconfidence,
    mismatch_reasons,
    official_screenshot_url,
    official_source_url,
    risk_level,
  } = report;

  const sizeIssue = discrepancies.find((d) => d.field === "size");

  // ── Brand row ───────────────────────────────────────────────
  const brandStatus: FieldStatus = match_type === "BRAND_NOT_FOUND" ? "fail" : "ok";
  const brandResult =
    match_type === "BRAND_NOT_FOUND"
      ? "Not in database"
      : match_context.brand_count
        ? `In database · ${match_context.brand_count} products`
        : "Confirmed";
  const brandDetail =
    match_type === "BRAND_NOT_FOUND" && match_context.known_brands
      ? `Known brands: ${match_context.known_brands.slice(0, 8).join(", ")}`
      : undefined;

  // ── Product line row ────────────────────────────────────────
  const plSkip = match_type === "BRAND_NOT_FOUND";
  const plStatus: FieldStatus = plSkip
    ? "skip"
    : match_type === "PRODUCT_LINE_NOT_FOUND"
      ? "fail"
      : "ok";
  const plResult = plSkip
    ? "not provided"
    : match_type === "PRODUCT_LINE_NOT_FOUND"
      ? "Not recognized"
      : "Recognized";
  const plDetail =
    match_type === "PRODUCT_LINE_NOT_FOUND" && match_context.known_product_lines
      ? `Known lines: ${match_context.known_product_lines.slice(0, 8).join(", ")}`
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
      ? "not provided — product line not identified"
      : "not provided"
    : match_type === "EXACT"
      ? "Exact match"
      : match_type === "FUZZY_COLORWAY"
        ? `No exact match — closest “${match_context.closest_colorway}” at ${Math.round(
            (match_context.best_fuzzy_score ?? 0) * 100,
          )}%`
        : "Not found in this product line";
  const cwDetail =
    !cwSkip && match_type !== "EXACT" && match_context.known_colorways?.length
      ? `Known colorways: ${match_context.known_colorways.join(", ")}`
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
    ? "not provided"
    : sizeIssue
      ? sizeIssue.message
          .split("officially offered sizes")
          .pop()
          ?.trim()
          .replace(/^\(|\)$/g, "") ?? "Size mismatch"
      : extracted.claimed_size
        ? "Officially offered"
        : "";

  // ── Verdict summary line ────────────────────────────────────
  const statuses: FieldStatus[] = [brandStatus, plStatus, cwStatus, sizeStatus];
  const checked = statuses.filter((s) => s !== "skip").length;
  const issues = statuses.filter((s) => s === "fail" || s === "warn").length;
  const verdictSub =
    risk_level === "low"
      ? "All checked details match the official record."
      : risk_level === "unverifiable"
        ? mismatch_reasons || "Not enough detail to identify this product."
        : `${issues} of ${checked} details didn’t match.`;

  const pct = Math.round((report.overall_score ?? 0) * 100);

  return (
    <div className="stack" style={{ gap: 0 }}>
      {/* verdict banner */}
      <div className={`verdict ${risk_level}`}>
        <div className="row">
          <span className="ico">{VERDICT_ICON[risk_level]}</span>
          <div style={{ flex: 1 }}>
            <div className="vtitle">{VERDICT_TITLE[risk_level]}</div>
            <div className="vsub">{verdictSub}</div>
          </div>
          <ConfidenceRing pct={pct} level={risk_level} />
        </div>
      </div>

      {/* breakdown */}
      <div className="label" style={{ margin: "18px 2px 9px" }}>
        Detail check
      </div>
      <div className="fields">
        <FieldRow status={brandStatus} label="Brand" claimed={extracted.claimed_brand} result={brandResult} detail={brandDetail} />
        <FieldRow status={plStatus} label="Product line" claimed={extracted.claimed_productline} result={plResult} detail={plDetail} />
        <FieldRow status={cwStatus} label="Colorway" claimed={extracted.claimed_colorway} result={cwResult} detail={cwDetail} />
        <FieldRow status={sizeStatus} label="Size" claimed={extracted.claimed_size} result={sizeResult} />
      </div>

      {/* official reference */}
      {official_screenshot_url?.startsWith("https://") ? (
        <>
          <div className="label" style={{ margin: "18px 2px 9px" }}>
            Official reference
          </div>
          <div className="card" style={{ padding: 13 }}>
            <div className="ref">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img className="pic" src={official_screenshot_url} alt="Official product" />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: 13.5 }}>
                  {expected_matchid ? "Matched record" : "Closest record"}
                </div>
                {expected_matchid ? (
                  <div className="mono" style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>
                    {expected_matchid}
                  </div>
                ) : (
                  <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>
                    No exact record matched
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
                    View on official site <ExtIcon />
                  </a>
                )}
              </div>
            </div>
          </div>
        </>
      ) : null}

      <p className="note" style={{ margin: "16px 6px 0" }}>
        This report flags mismatches against official records. It is not a determination of
        authenticity.
      </p>
    </div>
  );
}
