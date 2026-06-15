/**
 * TypeScript port of Data-Scrapers/scrapers/comparison_engine.py
 * Matching logic is identical — same thresholds, same cascade order.
 */

import { distance } from "fastest-levenshtein";
import type { AliasData } from "@/lib/supabase";
import type {
  VerifiedProduct,
  Report,
  Discrepancy,
  MatchType,
  MatchContext,
  Extracted,
} from "@/types/report";

const FUZZY_THRESHOLD = 0.75;
const ML_PER_OZ = 29.5735;

// ── Normalization ────────────────────────────────────────────────────────────

function normalize(s: string | null | undefined): string {
  if (!s) return "";
  return s.toLowerCase().replace(/[^\w\s]/g, "").trim();
}

function fuzzyScore(a: string | null | undefined, b: string | null | undefined): number {
  const na = normalize(a);
  const nb = normalize(b);
  if (!na && !nb) return 1;
  if (!na || !nb) return 0;
  const maxLen = Math.max(na.length, nb.length);
  if (maxLen === 0) return 1;
  return 1 - distance(na, nb) / maxLen;
}

// ── Matching ─────────────────────────────────────────────────────────────────

export interface MatchResult {
  row: VerifiedProduct | null;
  confidence: number;
  matchType: MatchType;
  matchContext: MatchContext;
}

export function findMatch(
  extracted: Extracted,
  reference: VerifiedProduct[],
  aliasData: AliasData
): MatchResult {
  const brand = extracted.claimed_brand ?? "";
  const productLine = extracted.claimed_productline ?? "";
  const colorway = extracted.claimed_colorway ?? "";
  const mainColors = (extracted.main_colors ?? "")
    .split(",")
    .map((c) => c.trim().toLowerCase())
    .filter(Boolean);

  const nb = normalize(brand);
  const npl = normalize(productLine);
  const nc = normalize(colorway);

  // ── Brand lookup ────────────────────────────────────────────────────────
  const brandRows = reference.filter((r) => normalize(r.brand) === nb);
  if (brandRows.length === 0) {
    const knownBrands = [...new Set(reference.map((r) => r.brand))].sort();
    return { row: null, confidence: 0, matchType: "BRAND_NOT_FOUND", matchContext: { known_brands: knownBrands } };
  }

  const brandCount = brandRows.length;

  // ── Product line lookup ─────────────────────────────────────────────────
  let plRows = brandRows.filter((r) => npl && normalize(r.product_line) === npl);
  if (plRows.length === 0) {
    plRows = brandRows.filter((r) => npl && fuzzyScore(productLine, r.product_line) >= FUZZY_THRESHOLD);
  }

  // ── Alias fallback for product line ─────────────────────────────────────
  if (plRows.length === 0) {
    outer: for (const [bKey, bData] of Object.entries(aliasData)) {
      if (normalize(bKey) !== nb) continue;
      for (const [officialPl, plData] of Object.entries(bData)) {
        for (const alias of plData.aliases ?? []) {
          if (normalize(npl) === normalize(alias) || fuzzyScore(productLine, alias) >= FUZZY_THRESHOLD) {
            const candidate = brandRows.filter((r) => normalize(r.product_line) === normalize(officialPl));
            if (candidate.length > 0) {
              plRows = candidate;
              break outer;
            }
          }
        }
      }
      break;
    }
  }

  if (plRows.length === 0) {
    const knownLines = [...new Set(brandRows.map((r) => r.product_line))].sort();
    return {
      row: null,
      confidence: 0,
      matchType: "PRODUCT_LINE_NOT_FOUND",
      matchContext: { brand_count: brandCount, known_product_lines: knownLines },
    };
  }

  const knownColorways = [...new Set(plRows.map((r) => r.colorway_name).filter(Boolean))].sort().slice(0, 10);

  // ── Tier 1 — exact colorway ─────────────────────────────────────────────
  for (const row of plRows) {
    if (nc && normalize(row.colorway_name) === nc) {
      return { row, confidence: 1.0, matchType: "EXACT", matchContext: { brand_count: brandCount } };
    }
  }

  // ── Tier 2 — fuzzy colorway ─────────────────────────────────────────────
  let bestRow: VerifiedProduct | null = null;
  let bestScore = 0;
  for (const row of plRows) {
    const score = fuzzyScore(colorway, row.colorway_name);
    if (score > bestScore) {
      bestScore = score;
      bestRow = row;
    }
  }

  if (bestScore >= FUZZY_THRESHOLD) {
    const span = 1.0 - FUZZY_THRESHOLD;
    const confidence = 0.6 + ((bestScore - FUZZY_THRESHOLD) / span) * 0.3;
    return {
      row: bestRow,
      confidence: Math.round(confidence * 100) / 100,
      matchType: "FUZZY_COLORWAY",
      matchContext: {
        brand_count: brandCount,
        best_fuzzy_score: bestScore,
        closest_colorway: bestRow?.colorway_name ?? "",
        known_colorways: knownColorways,
      },
    };
  }

  // ── Tier 3 — color-tag visual-color match ───────────────────────────────
  if (mainColors.length > 0) {
    const matchedPlNames = new Set(plRows.map((r) => normalize(r.product_line)));
    outer: for (const [bKey, bData] of Object.entries(aliasData)) {
      if (normalize(bKey) !== nb) continue;
      for (const [officialPl, plData] of Object.entries(bData)) {
        if (!matchedPlNames.has(normalize(officialPl))) continue;
        for (const [cwName, tags] of Object.entries(plData.colorways ?? {})) {
          const normTags = tags.map((t) => normalize(t));
          if (mainColors.some((mc) => normTags.includes(normalize(mc)))) {
            for (const row of plRows) {
              if (normalize(row.colorway_name) === normalize(cwName)) {
                return {
                  row,
                  confidence: 0.5,
                  matchType: "FUZZY_COLORWAY",
                  matchContext: {
                    brand_count: brandCount,
                    best_fuzzy_score: 0.5,
                    closest_colorway: cwName,
                    known_colorways: knownColorways,
                    color_tag_match: true,
                  },
                };
              }
            }
          }
        }
      }
      break outer;
    }
  }

  // ── Tier 4 — colorway not found ─────────────────────────────────────────
  return {
    row: plRows[0],
    confidence: 0.4,
    matchType: "COLORWAY_NOT_FOUND",
    matchContext: { brand_count: brandCount, known_colorways: knownColorways },
  };
}

// ── Field comparison ─────────────────────────────────────────────────────────

function toOz(s: string): number | null {
  const m = s.toLowerCase().match(/(\d+(?:\.\d+)?)\s*(ml|l|oz)?/);
  if (!m) return null;
  const val = parseFloat(m[1]);
  const unit = (m[2] ?? "").trim();
  if (unit === "ml") return val / ML_PER_OZ;
  if (unit === "l") return (val * 1000) / ML_PER_OZ;
  return val;
}

function close(a: number, b: number): boolean {
  return Math.abs(a - b) / Math.max(b, 1) < 0.05;
}

export function compareFields(
  extracted: Extracted,
  matchRow: VerifiedProduct,
  matchType: MatchType
): Discrepancy[] {
  const issues: Discrepancy[] = [];

  if (matchType === "FUZZY_COLORWAY") {
    issues.push({
      field: "colorway",
      severity: "medium",
      message: `Colorway '${extracted.claimed_colorway}' could not be verified (closest official: '${matchRow.colorway_name}')`,
    });
  } else if (matchType === "COLORWAY_NOT_FOUND") {
    issues.push({
      field: "colorway",
      severity: "high",
      message: `Colorway '${extracted.claimed_colorway || "(not specified)"}' has no official match in this product line`,
    });
  }

  const officialStatus = (matchRow.status ?? "").toLowerCase();
  if (["discontinu", "retired", "sold out"].some((w) => officialStatus.includes(w))) {
    issues.push({
      field: "status",
      severity: "high",
      message: `'${matchRow.colorway_name}' is marked as discontinued in official records`,
    });
  }

  const claimedSize = extracted.claimed_size ?? "";
  const sizesAvailable = matchRow.sizes_available ?? "";
  if (claimedSize && sizesAvailable) {
    const claimedNum = toOz(claimedSize);
    const availNums = sizesAvailable
      .split(",")
      .map((s) => toOz(s.trim()))
      .filter((n): n is number => n !== null);
    if (claimedNum !== null && availNums.length > 0 && !availNums.some((n) => close(claimedNum, n))) {
      issues.push({
        field: "size",
        severity: "medium",
        message: `Claimed size '${claimedSize}' is not among officially offered sizes (${sizesAvailable.trim()})`,
      });
    }
  }

  return issues;
}

// ── Report generation ────────────────────────────────────────────────────────

const UNVERIFIABLE_TYPES = new Set<MatchType>(["BRAND_NOT_FOUND"]);

function riskLevel(matchType: MatchType, issues: Discrepancy[]): Report["risk_level"] {
  if (UNVERIFIABLE_TYPES.has(matchType)) return "unverifiable";
  if (matchType === "PRODUCT_LINE_NOT_FOUND") return "high";
  const severities = new Set(issues.map((d) => d.severity));
  if (severities.has("high") || issues.length >= 2) return "high";
  if (severities.has("medium") || matchType === "FUZZY_COLORWAY" || matchType === "COLORWAY_NOT_FOUND")
    return "medium";
  return "low";
}

export function generateReport(
  extracted: Extracted,
  matchRow: VerifiedProduct | null,
  confidence: number,
  matchType: MatchType,
  issues: Discrepancy[],
  matchContext: MatchContext
): Report {
  const mismatches = issues.map((d) => d.message).join("; ");
  const fallback = UNVERIFIABLE_TYPES.has(matchType)
    ? "No official match found"
    : matchType === "PRODUCT_LINE_NOT_FOUND"
    ? "Brand confirmed but product line not found in official records"
    : "";

  return {
    risk_level: riskLevel(matchType, issues),
    match_type: matchType,
    expected_matchid: matchRow?.item_id ?? null,
    expected_matchconfidence: confidence,
    mismatch_reasons: mismatches || fallback,
    official_screenshot_url: matchRow?.screenshot_url ?? null,
    official_source_url: matchRow?.source_url ?? null,
    match_context: matchContext,
    discrepancies: issues,
    extracted,
    matched_product_line: matchRow?.product_line ?? undefined,
    matched_colorway_name: matchRow?.colorway_name ?? undefined,
  };
}

export function runComparison(
  extracted: Extracted,
  reference: VerifiedProduct[],
  aliasData: AliasData
): Report {
  const { row, confidence, matchType, matchContext } = findMatch(extracted, reference, aliasData);
  const issues = row ? compareFields(extracted, row, matchType) : [];
  return generateReport(extracted, row, confidence, matchType, issues, matchContext);
}
