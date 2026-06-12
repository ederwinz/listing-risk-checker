#!/usr/bin/env python3
"""
Listing risk comparison engine.

Compares extracted marketplace listing data against official reference data in
Supabase verified_products. Reports discrepancies using "no official match found"
/ "claim could not be verified" language — never "fake".

Usage:
  python scrapers/comparison_engine.py --screenshot inbox/photo.jpg
  python scrapers/comparison_engine.py --testing-id XHS-001
  python scrapers/comparison_engine.py --all
"""

import argparse
import anthropic
import csv
import difflib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import supabase_sync
from listing_extractor import extract_from_screenshot, EXTRACTION_PROMPT  # noqa: F401

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent

FUZZY_THRESHOLD = 0.75  # minimum SequenceMatcher ratio for a fuzzy colorway match


# ── Normalization ──────────────────────────────────────────────────────────────

def _normalize(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def _fuzzy(a: str | None, b: str | None) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


# ── Reference DB ───────────────────────────────────────────────────────────────

def load_reference_db() -> list[dict]:
    """Load all verified_products from Supabase, falling back to CSV."""
    rows = supabase_sync.load_all_verified()
    if rows:
        return rows
    csv_path = BASE_DIR / "Verified_Products.csv"
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return [
            {
                "item_id": r["Item ID"],
                "brand": r["Brand"],
                "product_line": r["Product Line"],
                "model_name": r["Model Name"],
                "colorway_name": r["Colorway Name"],
                "sizes_available": r["Sizes Available"],
                "status": r["Status"],
                "price": r["Price"],
                "sale_price": r["Sale Price"],
                "screenshot_url": r["Screenshot"],
                "source_url": r["Source URL"],
            }
            for r in csv.DictReader(f)
        ]


# ── Matching ───────────────────────────────────────────────────────────────────

def find_match(extracted: dict, reference: list[dict]) -> tuple[dict | None, float, str]:
    """
    Three-tier cascade:
      EXACT            — brand + product_line + colorway all normalize-equal
      FUZZY_COLORWAY   — brand + product_line exact; colorway fuzzy ≥ threshold
      PRODUCT_LINE_ONLY — brand + product_line exact; colorway below threshold
      NO_MATCH         — brand or product_line not found
    Returns (row, confidence, match_type).
    """
    brand = extracted.get("claimed_brand") or ""
    product_line = extracted.get("claimed_productline") or ""
    colorway = extracted.get("claimed_colorway") or ""

    nb = _normalize(brand)
    npl = _normalize(product_line)
    nc = _normalize(colorway)

    brand_rows = [r for r in reference if _normalize(r.get("brand")) == nb]
    if not brand_rows:
        return None, 0.0, "NO_MATCH"

    pl_rows = [r for r in brand_rows if npl and _normalize(r.get("product_line")) == npl]
    if not pl_rows:
        # Try fuzzy product-line match
        pl_rows = [
            r for r in brand_rows
            if npl and _fuzzy(product_line, r.get("product_line")) >= FUZZY_THRESHOLD
        ]
    if not pl_rows:
        return None, 0.0, "NO_MATCH"

    # Tier 1 — exact colorway
    for row in pl_rows:
        if nc and _normalize(row.get("colorway_name")) == nc:
            return row, 1.0, "EXACT"

    # Tier 2 — fuzzy colorway
    best_row, best_score = None, 0.0
    for row in pl_rows:
        score = _fuzzy(colorway, row.get("colorway_name"))
        if score > best_score:
            best_score, best_row = score, row

    if best_score >= FUZZY_THRESHOLD:
        # Scale confidence from 0.6 at threshold to 0.9 at perfect
        span = 1.0 - FUZZY_THRESHOLD
        confidence = 0.6 + (best_score - FUZZY_THRESHOLD) / span * 0.3
        return best_row, round(confidence, 2), "FUZZY_COLORWAY"

    # Tier 3 — product line only
    return pl_rows[0], 0.4, "PRODUCT_LINE_ONLY"


# ── Field comparison ───────────────────────────────────────────────────────────

_ML_PER_OZ = 29.5735

def _to_oz(s: str) -> float | None:
    """Convert a size string to fluid ounces for cross-unit comparison."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|l|oz)?", s.lower())
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").strip()
    if unit == "ml":
        return val / _ML_PER_OZ
    if unit == "l":
        return val * 1000 / _ML_PER_OZ
    return val  # oz or bare number


def compare_fields(extracted: dict, match_row: dict, match_type: str) -> list[dict]:
    """Returns list of {field, severity, message} discrepancy dicts."""
    issues: list[dict] = []

    # Colorway
    if match_type == "FUZZY_COLORWAY":
        claimed = extracted.get("claimed_colorway") or ""
        official = match_row.get("colorway_name") or ""
        issues.append({
            "field": "colorway",
            "severity": "medium",
            "message": (
                f"Colorway '{claimed}' could not be verified against official records "
                f"(closest official match: '{official}')"
            ),
        })
    elif match_type == "PRODUCT_LINE_ONLY":
        claimed = extracted.get("claimed_colorway") or "(not specified)"
        issues.append({
            "field": "colorway",
            "severity": "high",
            "message": f"Colorway '{claimed}' has no official match in this product line",
        })

    # Status — flag if product is discontinued
    official_status = (match_row.get("status") or "").lower()
    if any(w in official_status for w in ("discontinu", "retired", "sold out")):
        issues.append({
            "field": "status",
            "severity": "high",
            "message": (
                f"'{match_row.get('colorway_name')}' is marked as discontinued "
                "in official records"
            ),
        })

    # Size
    claimed_size = extracted.get("claimed_size") or ""
    sizes_available = match_row.get("sizes_available") or ""
    if claimed_size and sizes_available:
        claimed_num = _to_oz(claimed_size)
        avail_nums = [_to_oz(s) for s in sizes_available.split(",")]
        avail_nums = [n for n in avail_nums if n is not None]
        # Allow 5% tolerance to absorb ml↔oz rounding (e.g. 945 ml ≈ 32 oz)
        def _close(a: float, b: float) -> bool:
            return abs(a - b) / max(b, 1) < 0.05
        if claimed_num is not None and avail_nums and not any(_close(claimed_num, n) for n in avail_nums):
            issues.append({
                "field": "size",
                "severity": "medium",
                "message": (
                    f"Claimed size '{claimed_size}' is not among officially offered sizes "
                    f"({sizes_available.strip()})"
                ),
            })

    return issues


# ── Report generation ──────────────────────────────────────────────────────────

def _risk_level(match_type: str, issues: list[dict]) -> str:
    if match_type == "NO_MATCH":
        return "unverifiable"
    severities = {d["severity"] for d in issues}
    if "high" in severities or len(issues) >= 2:
        return "high"
    if "medium" in severities or match_type in ("FUZZY_COLORWAY", "PRODUCT_LINE_ONLY"):
        return "medium"
    return "low"


def generate_report(
    extracted: dict,
    match_row: dict | None,
    confidence: float,
    match_type: str,
    issues: list[dict],
) -> dict:
    risk = _risk_level(match_type, issues)
    brand = extracted.get("claimed_brand") or "Unknown brand"
    product_line = extracted.get("claimed_productline") or ""

    if match_type == "NO_MATCH":
        label = brand + (f" {product_line}" if product_line else "")
        summary = (
            f"No official reference found for {label} in our database. "
            "This listing could not be verified against official records."
        )
        mismatch_reasons = "No official match found"
    else:
        official_name = (
            f"{match_row['brand']} {match_row['product_line']} – {match_row['colorway_name']}"
        )
        if not issues:
            summary = (
                f"Official reference found: {official_name}. "
                "All checked fields match official records."
            )
        else:
            reasons_text = "; ".join(d["message"] for d in issues)
            summary = (
                f"Official reference found: {official_name}. "
                f"The following could not be fully verified: {reasons_text}"
            )
        mismatch_reasons = "; ".join(d["message"] for d in issues)

    return {
        "risk_level": risk,
        "expected_matchid": match_row["item_id"] if match_row else None,
        "expected_matchconfidence": confidence,
        "mismatch_reasons": mismatch_reasons,
        "official_screenshot_url": match_row.get("screenshot_url") if match_row else None,
        "official_source_url": match_row.get("source_url") if match_row else None,
        "human_summary": summary,
        "match_type": match_type,
        "discrepancies": issues,
    }


# ── Console output ─────────────────────────────────────────────────────────────

_RISK_ICON = {"low": "✓", "medium": "⚠", "high": "✗", "unverifiable": "?"}


def print_report(report: dict, extracted: dict):
    icon = _RISK_ICON.get(report["risk_level"], "?")
    brand = extracted.get("claimed_brand") or "?"
    pl = extracted.get("claimed_productline") or ""
    colorway = extracted.get("claimed_colorway") or "?"
    print(f"\n{'─'*60}")
    print(f"  {icon}  Risk: {report['risk_level'].upper()}")
    print(f"     Listing:  {brand} / {pl} / {colorway}")
    if report["expected_matchid"]:
        print(
            f"     Match:    {report['expected_matchid']}"
            f"  (confidence {report['expected_matchconfidence']:.0%})"
        )
    print(f"\n  {report['human_summary']}")
    if report["discrepancies"]:
        print("\n  Discrepancies:")
        for d in report["discrepancies"]:
            print(f"    [{d['severity'].upper()}] {d['message']}")
    if (report.get("official_screenshot_url") or "").startswith("https://"):
        print(f"\n  Official image: {report['official_screenshot_url']}")
    print(f"{'─'*60}")


# ── Supabase write ─────────────────────────────────────────────────────────────

def save_result(testing_id: str, report: dict):
    supabase_sync.update_listing_match(testing_id, {
        "expected_matchid": report["expected_matchid"] or "",
        "expected_matchconfidence": report["expected_matchconfidence"],
        "risk_level": report["risk_level"],
        "mismatch_reasons": report["mismatch_reasons"],
    })


# ── Core pipeline ──────────────────────────────────────────────────────────────

def run_comparison(extracted: dict, reference: list[dict]) -> dict:
    match_row, confidence, match_type = find_match(extracted, reference)
    issues = compare_fields(extracted, match_row, match_type) if match_row else []
    return generate_report(extracted, match_row, confidence, match_type, issues)


def _row_to_extracted(row: dict) -> dict:
    return {
        "claimed_brand": row.get("claimed_brand"),
        "claimed_productline": row.get("claimed_productline"),
        "claimed_colorway": row.get("claimed_colorway"),
        "claimed_size": row.get("claimed_size"),
        "claimed_status": row.get("claimed_status"),
        "platform": row.get("platform"),
        "seller_name": row.get("seller_name"),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compare marketplace listings against official reference data"
    )
    parser.add_argument("--screenshot", help="Path to a marketplace screenshot image")
    parser.add_argument(
        "--testing-id",
        help="Compare an existing test listing by ID (e.g. XHS-001)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Compare all test_listings rows that don't yet have a match result",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    print("Loading official reference database…")
    reference = load_reference_db()
    if not reference:
        print("ERROR: Could not load verified_products.")
        sys.exit(1)
    print(f"  {len(reference)} official products loaded.")

    client = anthropic.Anthropic(api_key=api_key)

    # ── Screenshot mode ──────────────────────────────────────────────────────
    if args.screenshot:
        image_path = Path(args.screenshot)
        if not image_path.exists():
            print(f"ERROR: File not found: {image_path}")
            sys.exit(1)
        print(f"\nExtracting from {image_path.name}…")
        try:
            extracted = extract_from_screenshot(image_path, client)
        except Exception as e:
            print(f"ERROR: Extraction failed: {e}")
            sys.exit(1)
        print(
            f"  Extracted: {extracted.get('claimed_brand')} / "
            f"{extracted.get('claimed_productline')} / "
            f"{extracted.get('claimed_colorway')}"
        )
        report = run_comparison(extracted, reference)
        print_report(report, extracted)

    # ── Testing-ID mode ──────────────────────────────────────────────────────
    elif args.testing_id:
        sb = supabase_sync._get_client()
        if not sb:
            print("ERROR: Supabase not configured.")
            sys.exit(1)
        resp = sb.table("test_listings").select("*").eq("testing_id", args.testing_id).execute()
        if not resp.data:
            print(f"ERROR: No test listing found for ID {args.testing_id}")
            sys.exit(1)
        extracted = _row_to_extracted(resp.data[0])
        report = run_comparison(extracted, reference)
        print_report(report, extracted)
        save_result(args.testing_id, report)
        print(f"\nResult saved to test_listings / {args.testing_id}.")

    # ── Batch mode ───────────────────────────────────────────────────────────
    elif args.all:
        print("\nFetching unmatched test listings…")
        rows = supabase_sync.load_unmatched_listings()
        if not rows:
            print("No unmatched listings found.")
            return
        print(f"  {len(rows)} listings to compare.\n")
        for row in rows:
            extracted = _row_to_extracted(row)
            report = run_comparison(extracted, reference)
            print_report(report, extracted)
            save_result(row["testing_id"], report)
        print(f"\nDone. {len(rows)} listings compared and results saved.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
