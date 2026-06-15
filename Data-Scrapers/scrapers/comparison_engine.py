#!/usr/bin/env python3
"""
Listing risk comparison engine.

Compares extracted marketplace listing data against official reference data in
Supabase verified_products. Reports discrepancies using "no official match found"
/ "claim could not be verified" language — never "fake".

Usage:
  python scrapers/comparison_engine.py --watch               # auto-process inbox/ (recommended)
  python scrapers/comparison_engine.py --screenshot photo.jpg
  python scrapers/comparison_engine.py --testing-id XHS-001
  python scrapers/comparison_engine.py --all
"""

import argparse
import anthropic
import csv
import difflib
import functools
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import supabase_sync
from listing_extractor import extract_from_screenshot, EXTRACTION_PROMPT  # noqa: F401

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
INBOX_DIR = BASE_DIR / "inbox"
PROCESSED_DIR = BASE_DIR / "processed"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

FUZZY_THRESHOLD = 0.75


# ── Aliases ────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _load_aliases() -> dict:
    return supabase_sync.load_aliases()


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

def find_match(
    extracted: dict, reference: list[dict]
) -> tuple[dict | None, float, str, dict]:
    """
    Match cascade with granular failure types.

    Match types:
      EXACT               — brand + product_line + colorway all normalize-equal
      FUZZY_COLORWAY      — brand + product_line exact; colorway fuzzy ≥ threshold
                            (also used for color-tag visual-color matches at 0.5 confidence)
      COLORWAY_NOT_FOUND  — brand + product_line exact; colorway below threshold
      PRODUCT_LINE_NOT_FOUND — brand found; product_line not matched (even via aliases)
      BRAND_NOT_FOUND     — brand not in reference db

    Returns (row, confidence, match_type, context).
    context holds database values useful for the report (known brands/lines/colorways).
    """
    brand = extracted.get("claimed_brand") or ""
    product_line = extracted.get("claimed_productline") or ""
    colorway = extracted.get("claimed_colorway") or ""
    main_colors = [
        c.strip().lower()
        for c in (extracted.get("main_colors") or "").split(",")
        if c.strip()
    ]

    nb = _normalize(brand)
    npl = _normalize(product_line)
    nc = _normalize(colorway)

    aliases_data = _load_aliases()

    # ── Brand lookup ────────────────────────────────────────────────────────
    brand_rows = [r for r in reference if _normalize(r.get("brand")) == nb]
    if not brand_rows:
        known_brands = sorted({r["brand"] for r in reference})
        return None, 0.0, "BRAND_NOT_FOUND", {"known_brands": known_brands}

    brand_count = len(brand_rows)

    # ── Product line lookup ─────────────────────────────────────────────────
    pl_rows = [r for r in brand_rows if npl and _normalize(r.get("product_line")) == npl]
    if not pl_rows:
        pl_rows = [
            r for r in brand_rows
            if npl and _fuzzy(product_line, r.get("product_line")) >= FUZZY_THRESHOLD
        ]

    # ── Alias fallback for product line ─────────────────────────────────────
    if not pl_rows:
        for b_key, b_data in aliases_data.items():
            if _normalize(b_key) != nb:
                continue
            for official_pl, pl_data in b_data.items():
                for alias in pl_data.get("aliases", []):
                    if (
                        _normalize(npl) == _normalize(alias)
                        or _fuzzy(product_line, alias) >= FUZZY_THRESHOLD
                    ):
                        candidate = [
                            r for r in brand_rows
                            if _normalize(r.get("product_line")) == _normalize(official_pl)
                        ]
                        if candidate:
                            pl_rows = candidate
                            break
                if pl_rows:
                    break
            break  # only one brand key matches

    if not pl_rows:
        known_lines = sorted({r["product_line"] for r in brand_rows})
        return None, 0.0, "PRODUCT_LINE_NOT_FOUND", {
            "brand_count": brand_count,
            "known_product_lines": known_lines,
        }

    known_colorways = sorted({r["colorway_name"] for r in pl_rows if r.get("colorway_name")})

    # ── Tier 1 — exact colorway ─────────────────────────────────────────────
    for row in pl_rows:
        if nc and _normalize(row.get("colorway_name")) == nc:
            return row, 1.0, "EXACT", {"brand_count": brand_count}

    # ── Tier 2 — fuzzy colorway ─────────────────────────────────────────────
    best_row, best_score = None, 0.0
    for row in pl_rows:
        score = _fuzzy(colorway, row.get("colorway_name"))
        if score > best_score:
            best_score, best_row = score, row

    if best_score >= FUZZY_THRESHOLD:
        span = 1.0 - FUZZY_THRESHOLD
        confidence = 0.6 + (best_score - FUZZY_THRESHOLD) / span * 0.3
        return best_row, round(confidence, 2), "FUZZY_COLORWAY", {
            "brand_count": brand_count,
            "best_fuzzy_score": best_score,
            "closest_colorway": best_row.get("colorway_name", ""),
            "known_colorways": known_colorways[:10],
        }

    # ── Tier 3 — color-tag visual-color match ───────────────────────────────
    if main_colors:
        matched_pl_names = {_normalize(r.get("product_line", "")) for r in pl_rows}
        for b_key, b_data in aliases_data.items():
            if _normalize(b_key) != nb:
                continue
            for official_pl, pl_data in b_data.items():
                if _normalize(official_pl) not in matched_pl_names:
                    continue
                for cw_name, tags in pl_data.get("colorways", {}).items():
                    norm_tags = [_normalize(t) for t in tags]
                    if any(_normalize(mc) in norm_tags for mc in main_colors):
                        for row in pl_rows:
                            if _normalize(row.get("colorway_name")) == _normalize(cw_name):
                                return row, 0.5, "FUZZY_COLORWAY", {
                                    "brand_count": brand_count,
                                    "best_fuzzy_score": 0.5,
                                    "closest_colorway": cw_name,
                                    "known_colorways": known_colorways[:10],
                                    "color_tag_match": True,
                                }
            break  # only one brand key matches

    # ── Tier 4 — product line only (colorway not found) ─────────────────────
    return pl_rows[0], 0.4, "COLORWAY_NOT_FOUND", {
        "brand_count": brand_count,
        "known_colorways": known_colorways[:10],
    }


# ── Field comparison ───────────────────────────────────────────────────────────

_ML_PER_OZ = 29.5735


def _to_oz(s: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|l|oz)?", s.lower())
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").strip()
    if unit == "ml":
        return val / _ML_PER_OZ
    if unit == "l":
        return val * 1000 / _ML_PER_OZ
    return val


def _close(a: float, b: float) -> bool:
    return abs(a - b) / max(b, 1) < 0.05


def compare_fields(extracted: dict, match_row: dict, match_type: str) -> list[dict]:
    issues: list[dict] = []

    if match_type == "FUZZY_COLORWAY":
        claimed = extracted.get("claimed_colorway") or ""
        official = match_row.get("colorway_name") or ""
        issues.append({
            "field": "colorway",
            "severity": "medium",
            "message": f"Colorway '{claimed}' could not be verified (closest official: '{official}')",
        })
    elif match_type == "COLORWAY_NOT_FOUND":
        claimed = extracted.get("claimed_colorway") or "(not specified)"
        issues.append({
            "field": "colorway",
            "severity": "high",
            "message": f"Colorway '{claimed}' has no official match in this product line",
        })

    official_status = (match_row.get("status") or "").lower()
    if any(w in official_status for w in ("discontinu", "retired", "sold out")):
        issues.append({
            "field": "status",
            "severity": "high",
            "message": f"'{match_row.get('colorway_name')}' is marked as discontinued in official records",
        })

    claimed_size = extracted.get("claimed_size") or ""
    sizes_available = match_row.get("sizes_available") or ""
    if claimed_size and sizes_available:
        claimed_num = _to_oz(claimed_size)
        avail_nums = [_to_oz(s) for s in sizes_available.split(",")]
        avail_nums = [n for n in avail_nums if n is not None]
        if claimed_num is not None and avail_nums and not any(_close(claimed_num, n) for n in avail_nums):
            issues.append({
                "field": "size",
                "severity": "medium",
                "message": f"Claimed size '{claimed_size}' is not among officially offered sizes ({sizes_available.strip()})",
            })

    return issues


# ── Report generation ──────────────────────────────────────────────────────────

_UNVERIFIABLE_TYPES = {"BRAND_NOT_FOUND"}


def _risk_level(match_type: str, issues: list[dict]) -> str:
    if match_type in _UNVERIFIABLE_TYPES:
        return "unverifiable"
    if match_type == "PRODUCT_LINE_NOT_FOUND":
        return "high"
    severities = {d["severity"] for d in issues}
    if "high" in severities or len(issues) >= 2:
        return "high"
    if "medium" in severities or match_type in ("FUZZY_COLORWAY", "COLORWAY_NOT_FOUND"):
        return "medium"
    return "low"


def generate_report(
    extracted: dict,
    match_row: dict | None,
    confidence: float,
    match_type: str,
    issues: list[dict],
    match_context: dict,
) -> dict:
    risk = _risk_level(match_type, issues)
    mismatch_reasons = "; ".join(d["message"] for d in issues) if issues else (
        "No official match found" if match_type in _UNVERIFIABLE_TYPES else (
            "Brand confirmed but product line not found in official records"
            if match_type == "PRODUCT_LINE_NOT_FOUND" else ""
        )
    )
    return {
        "risk_level": risk,
        "expected_matchid": match_row["item_id"] if match_row else None,
        "expected_matchconfidence": confidence,
        "mismatch_reasons": mismatch_reasons,
        "official_screenshot_url": match_row.get("screenshot_url") if match_row else None,
        "official_source_url": match_row.get("source_url") if match_row else None,
        "match_type": match_type,
        "match_context": match_context,
        "discrepancies": issues,
    }


# ── Console output ─────────────────────────────────────────────────────────────

_RISK_ICON = {"low": "✓", "medium": "⚠", "high": "✗", "unverifiable": "?"}
_W = 62  # report width


def _field_line(icon: str, label: str, claimed: str, result: str, detail: str = "") -> str:
    claimed_col = f'"{claimed}"' if claimed else "(not in listing)"
    line = f"    {icon}  {label:<14}{claimed_col:<22}→  {result}"
    return line + (f"\n       {'':<14}{detail}" if detail else "")


def print_report(report: dict, extracted: dict):
    icon = _RISK_ICON.get(report["risk_level"], "?")
    brand = extracted.get("claimed_brand") or "?"
    pl = extracted.get("claimed_productline") or ""
    colorway = extracted.get("claimed_colorway") or "?"
    ctx = report.get("match_context") or {}
    match_type = report["match_type"]

    print(f"\n{'─' * _W}")
    listing_str = f"{brand} / {pl} / {colorway}" if pl else f"{brand} / {colorway}"
    print(f"  {icon}  Risk: {report['risk_level'].upper()}   ·   {listing_str}")
    if report["expected_matchid"]:
        print(f"     Match: {report['expected_matchid']}  ({report['expected_matchconfidence']:.0%} confidence)")

    print(f"\n  Field Verification:")

    # ── Brand ──────────────────────────────────────────────────────────────
    if match_type == "BRAND_NOT_FOUND":
        known = ", ".join(ctx.get("known_brands", [])[:8])
        print(_field_line("✗", "Brand", brand, "not in database"))
        print(f"       {'':14}Known brands: {known}")
    else:
        count = ctx.get("brand_count", "")
        count_str = f"in database ({count} products)" if count else "confirmed"
        print(_field_line("✓", "Brand", brand, count_str))

    # ── Product Line ───────────────────────────────────────────────────────
    if match_type == "BRAND_NOT_FOUND":
        print(_field_line("–", "Product Line", pl, "not checked (brand not found)"))
    elif match_type == "PRODUCT_LINE_NOT_FOUND":
        known_lines = ctx.get("known_product_lines", [])
        print(_field_line("✗", "Product Line", pl, "not found in official records"))
        if known_lines:
            lines_str = ", ".join(known_lines[:8])
            print(f"       {'':14}Known lines: {lines_str}")
    else:
        print(_field_line("✓", "Product Line", pl, "confirmed"))

    # ── Colorway ───────────────────────────────────────────────────────────
    colorway_issues = [d for d in report["discrepancies"] if d["field"] == "colorway"]
    if match_type in _UNVERIFIABLE_TYPES or match_type == "PRODUCT_LINE_NOT_FOUND":
        print(_field_line("–", "Colorway", colorway, "not checked"))
    elif match_type == "EXACT":
        print(_field_line("✓", "Colorway", colorway, "exact match"))
    elif match_type == "FUZZY_COLORWAY":
        score = ctx.get("best_fuzzy_score", 0)
        closest = ctx.get("closest_colorway", "")
        known = ctx.get("known_colorways", [])
        if ctx.get("color_tag_match"):
            print(_field_line("⚠", "Colorway", colorway,
                              f"visual color match → \"{closest}\" (via color tag)"))
        else:
            print(_field_line("⚠", "Colorway", colorway,
                              f"no exact match (closest: \"{closest}\" at {score:.0%})"))
        if known:
            print(f"       {'':14}Known: {', '.join(known[:8])}")
    elif match_type == "COLORWAY_NOT_FOUND":
        known = ctx.get("known_colorways", [])
        print(_field_line("✗", "Colorway", colorway, "not found in this product line"))
        if known:
            print(f"       {'':14}Known: {', '.join(known[:8])}")

    # ── Size ───────────────────────────────────────────────────────────────
    claimed_size = extracted.get("claimed_size") or ""
    size_issues = [d for d in report["discrepancies"] if d["field"] == "size"]
    if match_type in _UNVERIFIABLE_TYPES or match_type == "PRODUCT_LINE_NOT_FOUND" or not report["expected_matchid"]:
        print(_field_line("–", "Size", claimed_size, "not checked"))
    elif size_issues:
        msg = size_issues[0]["message"]
        print(_field_line("✗", "Size", claimed_size, msg.split("officially offered sizes")[-1].strip("() ")))
    elif claimed_size:
        print(_field_line("✓", "Size", claimed_size, "confirmed"))
    else:
        print(_field_line("–", "Size", "", "not in listing"))

    # ── Official image ─────────────────────────────────────────────────────
    img_url = report.get("official_screenshot_url") or ""
    if img_url.startswith("https://"):
        print(f"\n  Official image: {img_url}")

    print(f"{'─' * _W}")


# ── Supabase write ─────────────────────────────────────────────────────────────

def save_result(testing_id: str, report: dict):
    supabase_sync.update_listing_match(testing_id, {
        "expected_matchid": report["expected_matchid"] or "",
        "expected_matchconfidence": report["expected_matchconfidence"],
        "risk_level": report["risk_level"],
        "mismatch_reasons": report["mismatch_reasons"],
    })


# ── Alias auto-logging ─────────────────────────────────────────────────────────

_CJK_RE = re.compile(r"[一-鿿]+")


def _try_log_alias(extracted: dict, match_row: dict, match_type: str, match_context: dict) -> None:
    """
    When a listing matches with solid confidence AND claimed_modelname contains both
    the official English product-line name and Chinese characters, log the Chinese
    segments as confirmed aliases to Supabase.
    """
    if match_context.get("color_tag_match"):
        return
    confidence = match_context.get("best_fuzzy_score", 1.0)
    if match_type == "FUZZY_COLORWAY" and confidence < 0.75:
        return

    modelname = extracted.get("claimed_modelname") or ""
    if not modelname or not _CJK_RE.search(modelname):
        return

    brand = match_row.get("brand") or ""
    official_pl = match_row.get("product_line") or ""
    official_cw = match_row.get("colorway_name") or ""
    wrote_any = False

    # Product-line aliases — English anchor must appear in modelname
    if official_pl and _normalize(official_pl).split()[0] in _normalize(modelname):
        seqs = [s for s in _CJK_RE.findall(modelname) if len(s) >= 2]
        for seq in seqs:
            supabase_sync.upsert_product_line_alias(brand, official_pl, seq)
            print(f"  ✦  alias logged  \"{seq}\" → {official_pl}  ({brand})")
            wrote_any = True

    # Colorway color-tag aliases — EXACT match only
    if match_type == "EXACT" and official_cw:
        cw_anchor = _normalize(official_cw).split()[0]
        if cw_anchor and cw_anchor in _normalize(modelname):
            seqs = [s for s in _CJK_RE.findall(modelname) if len(s) >= 2]
            for seq in seqs:
                supabase_sync.upsert_colorway_alias(brand, official_pl, official_cw, seq)
                print(f"  ✦  color tag logged  \"{seq}\" → {official_cw}  ({brand} / {official_pl})")
                wrote_any = True

    if wrote_any:
        _load_aliases.cache_clear()


# ── Core pipeline ──────────────────────────────────────────────────────────────

def run_comparison(extracted: dict, reference: list[dict]) -> dict:
    match_row, confidence, match_type, match_context = find_match(extracted, reference)
    issues = compare_fields(extracted, match_row, match_type) if match_row else []
    if match_row:
        _try_log_alias(extracted, match_row, match_type, match_context)
    return generate_report(extracted, match_row, confidence, match_type, issues, match_context)


def _process_image(image_path: Path, client: anthropic.Anthropic, reference: list[dict],
                   move_after: bool = False):
    """Extract, compare, print. Optionally move to processed/."""
    print(f"\nExtracting from {image_path.name}…")
    try:
        extracted = extract_from_screenshot(image_path, client)
    except Exception as e:
        print(f"  ERROR: extraction failed — {e}")
        return
    print(
        f"  Extracted: {extracted.get('claimed_brand')} / "
        f"{extracted.get('claimed_productline')} / "
        f"{extracted.get('claimed_colorway')}"
    )
    report = run_comparison(extracted, reference)
    print_report(report, extracted)

    if move_after:
        dest_dir = PROCESSED_DIR / datetime.now().strftime("%Y-%m-%d")
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(image_path), str(dest_dir / image_path.name))


def _row_to_extracted(row: dict) -> dict:
    return {
        "claimed_brand": row.get("claimed_brand"),
        "claimed_productline": row.get("claimed_productline"),
        "claimed_colorway": row.get("claimed_colorway"),
        "claimed_modelname": row.get("claimed_modelname"),
        "claimed_size": row.get("claimed_size"),
        "claimed_status": row.get("claimed_status"),
        "main_colors": row.get("main_colors"),
        "platform": row.get("platform"),
        "seller_name": row.get("seller_name"),
    }


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compare marketplace listings against official reference data"
    )
    parser.add_argument("--watch", action="store_true",
                        help="Watch inbox/ and auto-compare new screenshots (Ctrl+C to stop)")
    parser.add_argument("--screenshot", help="Path to a marketplace screenshot image")
    parser.add_argument("--testing-id", help="Compare an existing test listing by ID (e.g. XHS-001)")
    parser.add_argument("--all", action="store_true",
                        help="Compare all test_listings rows that don't yet have a match result")
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

    # ── Watch mode ───────────────────────────────────────────────────────────
    if args.watch:
        INBOX_DIR.mkdir(exist_ok=True)
        seen = {p.name for p in INBOX_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS}
        print(f"\nWatching {INBOX_DIR}  (Ctrl+C to stop)…")
        try:
            while True:
                time.sleep(2)
                current = {p for p in INBOX_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS}
                new_files = sorted(p for p in current if p.name not in seen)
                for image_path in new_files:
                    seen.add(image_path.name)
                    _process_image(image_path, client, reference, move_after=True)
                seen = {p.name for p in INBOX_DIR.iterdir() if p.suffix.lower() in IMAGE_EXTS}
        except KeyboardInterrupt:
            print("\nStopped.")

    # ── Screenshot mode ──────────────────────────────────────────────────────
    elif args.screenshot:
        image_path = Path(args.screenshot)
        if not image_path.exists():
            print(f"ERROR: File not found: {image_path}")
            sys.exit(1)
        _process_image(image_path, client, reference)

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
