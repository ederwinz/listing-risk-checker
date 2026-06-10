#!/usr/bin/env python3
"""
Automated brand discovery: screenshots Chinese marketplace search results,
uses Claude Haiku vision to extract overseas brand names, scores by frequency
and platform weight, then probes Shopify for open APIs.

Usage:
    cd Data-Scrapers
    python scrapers/brand_scout.py --all
    python scrapers/brand_scout.py --category fitness --platform Rednote
    python scrapers/brand_scout.py --all \\
        --user-data-dir "/Users/you/Library/Application Support/Google/Chrome/Default"
    python scrapers/brand_scout.py --all --dry-run   # skip Shopify probing
"""

import argparse
import anthropic
import base64
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sheets_sync import append_rows as sheets_append

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
VERIFIED_CSV = BASE_DIR / "Verified_Products.csv"
CANDIDATES_CSV = BASE_DIR / "Brand_Candidates.csv"
SCOUTS_DIR = BASE_DIR / "brand_scouts"

CANDIDATES_COLUMNS = [
    "Run Date", "Brand Name", "Score", "Mention Count", "Category",
    "Platforms Seen", "Evidence", "Shopify Status", "Shopify Handle",
    "Recommended Action",
]

# ── Config ─────────────────────────────────────────────────────────────────────

PLATFORM_WEIGHTS = {"Rednote": 1.5, "Xianyu": 1.2, "Taobao": 1.0}
MENTION_THRESHOLD = 3.0

SEARCH_QUERIES = [
    # Fitness / activewear
    {"platform": "Rednote", "query": "美国健身品牌 leggings",        "category": "fitness"},
    {"platform": "Rednote", "query": "美国运动品牌推荐 gym wear",    "category": "fitness"},
    {"platform": "Rednote", "query": "海外代购 leggings brand",      "category": "fitness"},
    {"platform": "Rednote", "query": "海外健身品牌 bra shorts",      "category": "fitness"},
    {"platform": "Xianyu",  "query": "美国品牌 gym leggings",       "category": "fitness"},
    {"platform": "Xianyu",  "query": "海外健身品牌 运动裤",          "category": "fitness"},
    {"platform": "Taobao",  "query": "美国代购 健身品牌 leggings",   "category": "fitness"},
    {"platform": "Taobao",  "query": "海外运动品牌 代购",            "category": "fitness"},
    # Beauty / skincare
    {"platform": "Rednote", "query": "美国护肤品推荐 skincare",      "category": "beauty"},
    {"platform": "Rednote", "query": "海外美妆品牌 lip balm",        "category": "beauty"},
    {"platform": "Xianyu",  "query": "美国护肤品 正品",              "category": "beauty"},
    {"platform": "Taobao",  "query": "美国护肤品 代购",              "category": "beauty"},
    # Accessories / lifestyle
    {"platform": "Rednote", "query": "海外品牌 水杯 bottle",         "category": "accessories"},
    {"platform": "Rednote", "query": "美国生活方式品牌 lifestyle",    "category": "accessories"},
    {"platform": "Xianyu",  "query": "美国品牌 水杯 保温杯",         "category": "accessories"},
    # Streetwear
    {"platform": "Rednote", "query": "美国潮牌 streetwear brand",    "category": "streetwear"},
    {"platform": "Taobao",  "query": "美国潮牌 代购 hoodie",         "category": "streetwear"},
]

# Chinese transliteration → canonical English name (grow this over time)
BRAND_ALIASES: dict[str, str] = {
    "欧娜": "Owala",
    "斯坦利": "Stanley",
    "露露柠檬": "Lululemon",
    "安德玛": "Under Armour",
    "耐克": "Nike",
    "阿迪达斯": "Adidas",
    "优衣库": "Uniqlo",
    "始祖鸟": "Arc'teryx",
    "始祖鸟": "Arc'teryx",
    "巴塔哥尼亚": "Patagonia",
}

# Known domestic Chinese brands to ignore if the LLM slips them through
DOMESTIC_BRANDS = {
    # Chinese domestic apparel/sports
    "anta", "li-ning", "lining", "li ning", "peak", "xtep",
    # Chinese domestic beauty
    "perfect diary", "florasis", "judydoll", "colorkey", "mac", "hera",
    "proya", "winona", "homefacial pro",
    # Universities and institutions (not clothing brands)
    "mit", "harvard", "yale", "columbia", "stanford", "princeton",
    "oxford", "cambridge", "nyu", "ucla", "usc",
    # Generic words Claude sometimes mis-extracts as brands
    "claude", "anthropic", "openai",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; brand-scout/1.0)"}

BRAND_EXTRACTION_PROMPT = """You are scanning a Chinese marketplace search results page to identify overseas (non-Chinese) clothing, beauty, or accessories BRANDS being sold or discussed by Chinese consumers.

Platform: {platform}
Category hint: {category}

A qualifying brand is a COMMERCIAL PRODUCT BRAND — a company that manufactures and sells physical products (apparel, skincare, accessories, gear). Only include it if it appears in the context of someone buying, selling, or reviewing that brand's products.

Include:
- English brand names in Roman letters (e.g. Gymshark, Owala, Alphalete)
- Chinese transliterations of foreign brands (e.g. 欧娜 = Owala, 露露柠檬 = Lululemon)
- Brand names mixing Chinese and English (e.g. "lululemon瑜伽裤")

EXCLUDE — do not extract these even if visible on screen:
- Universities, colleges, or institutions (MIT, Columbia, Harvard, Stanford, etc.) — these are NOT clothing brands
- Chinese domestic brands (Anta, Li-Ning, Perfect Diary, Florasis, etc.)
- Generic product words (leggings, 瑜伽裤, skincare, gym wear, 运动服)
- Platform names (Taobao, Xianyu, Rednote, 闲鱼, 淘宝, 小红书)
- Non-brand words (代购, 正品, 海外, 美国, 推荐)
- Text visible in the background or on unrelated graphics (logos of places, events, etc.)
- Nike, Adidas, Under Armour (too mainstream to be useful)

Return ONLY a valid JSON array — no explanation, no markdown fences:
[
  {{
    "brand": "The brand name in English (translate/romanize if you saw it in Chinese)",
    "chinese_name": "The Chinese transliteration if you saw one, otherwise null",
    "evidence": "1-sentence snippet showing this was a product brand being sold/discussed",
    "confidence": "high | medium | low"
  }}
]

Return [] if no qualifying commercial product brands are visible. When in doubt, do not include."""


# ── URL builders ───────────────────────────────────────────────────────────────

def build_search_url(platform: str, query: str, page: int = 1) -> str | None:
    q = quote(query)
    if platform == "Rednote":
        # page 2+ handled via JS scroll, not URL change
        return f"https://www.xiaohongshu.com/search_result?keyword={q}&type=51"
    if platform == "Xianyu":
        return f"https://www.xianyu.com/search?q={q}&page={page}"
    if platform == "Taobao":
        offset = (page - 1) * 44
        return f"https://s.taobao.com/search?q={q}&s={offset}"
    return None


# ── Screenshot ─────────────────────────────────────────────────────────────────

def screenshot_search_page(
    url: str,
    platform: str,
    query_slug: str,
    page_num: int,
    user_data_dir: str | None,
    output_dir: Path,
) -> Path | None:
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / f"{platform}_{query_slug}_p{page_num}.png"

    # Already captured on a previous run — reuse
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest

    timeout = 45_000 if platform == "Taobao" else 30_000

    try:
        with sync_playwright() as p:
            if user_data_dir:
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    viewport={"width": 768, "height": 1024},
                )
            else:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    viewport={"width": 768, "height": 1024},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )

            page = ctx.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout)
                time.sleep(3)

                if page_num > 1 and platform == "Rednote":
                    # Rednote uses infinite scroll — scroll to load more posts
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(3)

                page.screenshot(path=str(dest), full_page=False)
            finally:
                ctx.close()
    except Exception as e:
        print(f"    WARN: screenshot failed for {platform} p{page_num}: {e}")
        return None

    if dest.stat().st_size < 50_000:
        print(f"    WARN: screenshot too small ({dest.stat().st_size}B) — likely login wall, skipping")
        return None

    return dest


def screenshot_rednote_app(query: str, page: int, dest: Path) -> Path | None:
    """
    Search the Rednote Mac app and screenshot results.
    Requires Accessibility permission: System Settings → Privacy & Security →
    Accessibility → enable Terminal (or whichever app runs this script).
    """
    import subprocess as _sp

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Already captured on a previous run — reuse
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest

    # Activate app and type search query
    safe_query = query.replace('"', '\\"')
    search_script = f"""
    tell application "Rednote" to activate
    delay 1.5
    tell application "System Events"
        tell process "Rednote"
            keystroke "f" using {{command down}}
            delay 0.8
            keystroke "{safe_query}"
            key code 36
        end tell
    end tell
    """
    _sp.run(["osascript", "-e", search_script], capture_output=True)
    time.sleep(3)

    # Scroll down for pages beyond 1
    if page > 1:
        scroll_script = f"""
        tell application "System Events"
            tell process "Rednote"
                repeat {(page - 1) * 8} times
                    key code 125
                    delay 0.05
                end repeat
            end tell
        end tell
        """
        _sp.run(["osascript", "-e", scroll_script], capture_output=True)
        time.sleep(2)

    # Get window bounds and capture just the Rednote window
    bounds_script = """
    tell application "System Events"
        tell process "Rednote"
            get position of front window & size of front window
        end tell
    end tell
    """
    result = _sp.run(["osascript", "-e", bounds_script], capture_output=True, text=True)
    try:
        coords = [int(v.strip()) for v in result.stdout.strip().split(",")]
        x, y, w, h = coords
        _sp.run(["screencapture", "-R", f"{x},{y},{w},{h}", "-o", str(dest)])
    except Exception:
        _sp.run(["screencapture", "-o", str(dest)])  # fallback: full screen

    if dest.exists() and dest.stat().st_size > 50_000:
        return dest

    print(f"    WARN: app screenshot too small or missing — check Accessibility permissions")
    return None


# ── Extraction ─────────────────────────────────────────────────────────────────

def encode_image(image_path: Path) -> tuple[str, str]:
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }
    media_type = media_types.get(image_path.suffix.lower(), "image/png")
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def extract_brands_from_screenshot(
    image_path: Path,
    platform: str,
    category: str,
    client: anthropic.Anthropic,
) -> list[dict]:
    image_data, media_type = encode_image(image_path)
    prompt = BRAND_EXTRACTION_PROMPT.format(platform=platform, category=category)
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        response = message.content[0].text.strip()
        if response.startswith("```"):
            response = "\n".join(response.splitlines()[1:-1])
        return json.loads(response)
    except Exception as e:
        print(f"    WARN: extraction failed: {e}")
        return []


# ── Aggregation ────────────────────────────────────────────────────────────────

def normalize_brand(name: str) -> str:
    name = name.strip()
    # Apply alias map (Chinese → English)
    if name in BRAND_ALIASES:
        return BRAND_ALIASES[name]
    return name


def aggregate_mentions(
    raw_results: list[dict],
) -> dict[str, dict]:
    """
    raw_results items: {brand, chinese_name, evidence, confidence, platform, category, query}
    Returns {normalized_lower: {display_name, count, score, platforms, categories, evidence_samples, chinese_names}}
    """
    aggregated: dict[str, dict] = {}

    for item in raw_results:
        raw_brand = item.get("brand", "").strip()
        if not raw_brand:
            continue
        display = normalize_brand(raw_brand)
        if not display:
            continue

        key = display.lower()
        if key in DOMESTIC_BRANDS:
            continue

        confidence = item.get("confidence", "low")
        conf_weight = {"high": 1.0, "medium": 0.7, "low": 0.3}.get(confidence, 0.3)
        platform = item.get("platform", "")
        plat_weight = PLATFORM_WEIGHTS.get(platform, 1.0)
        item_score = plat_weight * conf_weight

        if key not in aggregated:
            aggregated[key] = {
                "display_name": display,
                "count": 0,
                "score": 0.0,
                "platform_counts": {},
                "categories": set(),
                "evidence_samples": [],
                "chinese_names": set(),
            }

        entry = aggregated[key]
        entry["count"] += 1
        entry["score"] = round(entry["score"] + item_score, 2)
        entry["platform_counts"][platform] = entry["platform_counts"].get(platform, 0) + 1
        entry["categories"].add(item.get("category", ""))

        evidence = item.get("evidence", "")
        if evidence and len(entry["evidence_samples"]) < 3:
            entry["evidence_samples"].append(evidence)

        chinese_name = item.get("chinese_name")
        if chinese_name:
            entry["chinese_names"].add(chinese_name)

    return aggregated


def filter_known_brands(aggregated: dict[str, dict], known_brands: set[str]) -> dict[str, dict]:
    return {k: v for k, v in aggregated.items() if k not in known_brands}


def load_known_brands() -> set[str]:
    known = set()
    if VERIFIED_CSV.exists():
        with open(VERIFIED_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                brand = row.get("Brand", "").strip().lower()
                if brand:
                    known.add(brand)
    return known


# ── Shopify probe ──────────────────────────────────────────────────────────────

def probe_shopify(brand_name: str) -> dict:
    """
    Inlined version of discover_brand() that returns structured data.
    Returns {"status": "open"|"locked"|"unknown", "handle": str|None}
    """
    import requests

    domain = brand_name.lower().replace(" ", "").replace("'", "").replace("-", "")
    stems = [domain, f"{domain}-us", f"shop-{domain}", f"{domain}skin", f"{domain}beauty"]

    for stem in stems:
        test_url = f"https://{stem}.myshopify.com/collections.json"
        try:
            resp = requests.get(
                test_url,
                headers=HEADERS,
                timeout=8,
                params={"limit": 1},
            )
        except Exception:
            continue

        if resp.status_code != 200:
            continue

        try:
            data = resp.json()
            if "collections" in data:
                return {"status": "open", "handle": stem}
        except Exception:
            # 200 but non-JSON = locked store
            return {"status": "locked", "handle": stem}

    return {"status": "unknown", "handle": None}


# ── Output ─────────────────────────────────────────────────────────────────────

def build_recommended_action(brand: str, shopify_status: str, shopify_handle: str | None) -> str:
    stem = brand.lower().replace(" ", "").replace("'", "")
    if shopify_status == "open":
        return f"open Shopify → python scrapers/official_scraper.py --discover https://{stem}.com"
    if shopify_status == "locked":
        return "locked Shopify → use official_page_scraper.py with product page URLs"
    return f"unknown → manual check: https://{stem}.com"


def write_candidates_csv(candidates: list[dict]) -> None:
    file_exists = CANDIDATES_CSV.exists()
    with open(CANDIDATES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANDIDATES_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(candidates)


def print_action_report(candidates: list[dict], run_date: str) -> None:
    open_brands = [c for c in candidates if c["Shopify Status"] == "open"]
    locked_brands = [c for c in candidates if c["Shopify Status"] == "locked"]
    unknown_brands = [c for c in candidates if c["Shopify Status"] == "unknown"]

    print(f"\n{'=' * 60}")
    print(f"BRAND SCOUT RESULTS — {run_date}")
    print(f"{'=' * 60}")
    print(f"{len(candidates)} new brand candidate(s) above threshold\n")

    if open_brands:
        print("── OPEN SHOPIFY (ready to scrape) ──────────────────────────")
        for c in open_brands:
            print(f"  {c['Brand Name']:<20}  score={c['Score']}  mentions={c['Mention Count']}")
            print(f"    → {c['Recommended Action']}")
            if c.get("Evidence"):
                print(f"    Evidence: {c['Evidence'][:80]}")
        print()

    if locked_brands:
        print("── LOCKED SHOPIFY (use page scraper) ───────────────────────")
        for c in locked_brands:
            print(f"  {c['Brand Name']:<20}  score={c['Score']}")
            print(f"    → {c['Recommended Action']}")
        print()

    if unknown_brands:
        print("── UNKNOWN (manual check) ───────────────────────────────────")
        for c in unknown_brands:
            print(f"  {c['Brand Name']:<20}  score={c['Score']}")
            print(f"    → {c['Recommended Action']}")
        print()

    print(f"Full results saved to: {CANDIDATES_CSV.name}")
    print(f"{'=' * 60}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scout Chinese marketplaces for trending overseas brands"
    )
    parser.add_argument("--all", action="store_true", help="Run all configured queries")
    parser.add_argument("--category", help="Only run queries for this category (fitness, beauty, accessories)")
    parser.add_argument("--platform", help="Only run queries for this platform (Rednote, Xianyu, Taobao)")
    parser.add_argument("--user-data-dir", dest="user_data_dir",
                        help="Chrome profile directory for logged-in sessions")
    parser.add_argument("--threshold", type=float, default=MENTION_THRESHOLD,
                        help=f"Minimum score to include in output (default {MENTION_THRESHOLD})")
    parser.add_argument("--pages", type=int, default=2,
                        help="Result pages to screenshot per query (default 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extract brands only, skip Shopify probing")
    parser.add_argument("--use-app", action="store_true",
                        help="Use Rednote Mac app instead of browser (Rednote queries only)")
    parser.add_argument("--screenshots-only", action="store_true",
                        help="Take screenshots only, skip Claude extraction (run VPN-off first, then re-run VPN-on)")
    parser.add_argument("--auto-scrape", action="store_true",
                        help="Automatically scrape brands found with open Shopify into Verified_Products")
    args = parser.parse_args()

    if not args.all and not args.category and not args.platform:
        parser.print_help()
        print("\nExample: python scrapers/brand_scout.py --all")
        return

    client = None
    if not args.screenshots_only:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not set in .env")
            return
        client = anthropic.Anthropic(api_key=api_key)
    run_date = datetime.now().strftime("%Y-%m-%d")
    output_dir = SCOUTS_DIR / run_date

    # Filter queries
    queries = SEARCH_QUERIES
    if args.category:
        queries = [q for q in queries if q["category"] == args.category]
    if args.platform:
        queries = [q for q in queries if q["platform"] == args.platform]

    if not queries:
        print(f"No queries matched filters (category={args.category}, platform={args.platform})")
        return

    print(f"\n=== Brand Scout — {run_date} ===")
    print(f"Running {len(queries)} query/queries, {args.pages} page(s) each")
    if not args.user_data_dir:
        print("TIP: pass --user-data-dir for better results (avoids login walls)\n")

    known_brands = load_known_brands()
    raw_results: list[dict] = []
    screenshots_taken = 0
    screenshots_skipped = 0

    for q in queries:
        platform = q["platform"]
        query = q["query"]
        category = q["category"]
        slug = re.sub(r"[^\w]", "_", query)[:30]

        print(f"\n  [{platform}] {query}")

        for page_num in range(1, args.pages + 1):
            url = build_search_url(platform, query, page_num)
            if not url:
                continue

            if args.use_app and platform == "Rednote":
                dest = output_dir / f"{platform}_{slug}_p{page_num}.png"
                img_path = screenshot_rednote_app(query, page_num, dest)
            else:
                img_path = screenshot_search_page(
                    url, platform, slug, page_num, args.user_data_dir, output_dir
                )

            if img_path is None:
                screenshots_skipped += 1
                continue

            screenshots_taken += 1

            if args.screenshots_only:
                print(f"    p{page_num}: screenshot saved")
                continue

            brands = extract_brands_from_screenshot(img_path, platform, category, client)

            for b in brands:
                b["platform"] = platform
                b["category"] = category
                b["query"] = query
            raw_results.extend(brands)

            found_names = [b["brand"] for b in brands]
            if found_names:
                print(f"    p{page_num}: {', '.join(found_names[:8])}{'...' if len(found_names) > 8 else ''}")
            else:
                print(f"    p{page_num}: (no brands found)")

            time.sleep(2)

    print(f"\n  Screenshots: {screenshots_taken} taken, {screenshots_skipped} skipped")
    print(f"  Raw brand mentions: {len(raw_results)}")

    if not raw_results:
        print("\nNo brand mentions extracted. Try running with --user-data-dir.")
        return

    # Save raw extractions for debugging
    raw_json = output_dir / "raw_extractions.json"
    raw_json.write_text(json.dumps(raw_results, ensure_ascii=False, indent=2), encoding="utf-8")

    # Aggregate and filter
    aggregated = aggregate_mentions(raw_results)
    new_brands = filter_known_brands(aggregated, known_brands)

    candidates_above = {k: v for k, v in new_brands.items() if v["score"] >= args.threshold}
    candidates_sorted = sorted(candidates_above.values(), key=lambda x: x["score"], reverse=True)

    if not candidates_sorted:
        print(f"\nNo new brand candidates above threshold ({args.threshold}). "
              f"Known/existing brands seen: {len(aggregated) - len(new_brands)}")
        return

    # Probe Shopify
    output_rows: list[dict] = []
    for entry in candidates_sorted:
        brand = entry["display_name"]

        if args.dry_run:
            shopify_status, shopify_handle = "unknown", None
        else:
            print(f"  Probing Shopify: {brand}...", end=" ", flush=True)
            result = probe_shopify(brand)
            shopify_status = result["status"]
            shopify_handle = result["handle"]
            print(shopify_status)
            time.sleep(1)

        row = {
            "Run Date": run_date,
            "Brand Name": brand,
            "Score": entry["score"],
            "Mention Count": entry["count"],
            "Category": ", ".join(entry["categories"]),
            "Platforms Seen": ", ".join(
                f"{p}×{c}" for p, c in sorted(entry["platform_counts"].items())
            ),
            "Evidence": " | ".join(entry["evidence_samples"])[:200],
            "Shopify Status": shopify_status,
            "Shopify Handle": shopify_handle or "",
            "Recommended Action": build_recommended_action(brand, shopify_status, shopify_handle),
        }
        output_rows.append(row)

    write_candidates_csv(output_rows)

    tab = os.environ.get("BRAND_CANDIDATES_TAB", "Brand_Candidates")
    sheets_append(tab, output_rows, CANDIDATES_COLUMNS)

    print_action_report(output_rows, run_date)

    if args.auto_scrape and not args.dry_run:
        open_brands = [r for r in output_rows if r["Shopify Status"] == "open"]
        if open_brands:
            print(f"\n=== Auto-scraping {len(open_brands)} open-Shopify brand(s) ===")
            sys.path.insert(0, str(Path(__file__).parent))
            from official_scraper import scrape_brand_dynamic
            total_new = 0
            for r in open_brands:
                total_new += scrape_brand_dynamic(r["Brand Name"], r["Shopify Handle"])
            print(f"\n✓ Auto-scrape complete — {total_new} total new rows added to Verified_Products")
        else:
            print("\nNo open-Shopify brands found this run — nothing to auto-scrape.")


if __name__ == "__main__":
    main()
