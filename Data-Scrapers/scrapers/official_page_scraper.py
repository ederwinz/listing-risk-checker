#!/usr/bin/env python3
"""
Extract official product data from brand website pages into Verified_Products.csv.

Use this for brands that do NOT expose a public Shopify API (e.g. Glossier, Stanley).
Point it at official product collection pages — it screenshots each page and uses
Claude vision to extract the product name and ALL visible colorways/shades.
Each colorway becomes a separate row in Verified_Products.csv.

Usage:
    cd Data-Scrapers
    python scrapers/official_page_scraper.py \\
        --brand Glossier \\
        --product-line "Balm Dotcom" \\
        --id-prefix glossier-balmdotcom \\
        --urls glossier_urls.txt

    # glossier_urls.txt — one official product page URL per line:
    # https://glossier.com/products/balm-dotcom
    # https://glossier.com/products/you-solid-perfume
"""

import argparse
import anthropic
import base64
import csv
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sheets_sync import append_rows as sheets_append
import supabase_sync

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
VERIFIED_CSV = BASE_DIR / "Verified_Products.csv"
SCREENSHOTS_DIR = BASE_DIR.parent / "Product Screenshots"

CSV_COLUMNS = [
    "Item ID", "Brand", "Product Line", "Model Name", "Colorway Name",
    "Sizes Available", "Status", "Price", "Sale Price", "Regions",
    "Trust Level", "Source Type", "Source URL", "Screenshot", "Notes",
]

EXTRACTION_PROMPT = """You are extracting structured product reference data from an official brand website page.

Look at the page carefully and identify ALL available colorways, shades, or variants (color swatches, shade name buttons, dropdowns). Include every option visible — do not skip any.

Return ONLY a valid JSON object — no explanation, no markdown fences.

{
  "product_name": "The product's official name exactly as labeled on the page (e.g. Balm Dotcom)",
  "price": "Price as shown (e.g. $14.00)",
  "sale_price": "Sale/reduced price if displayed, otherwise null",
  "sizes_available": "Comma-separated sizes if the product has size variants (e.g. '0.49 oz' or '30ml, 50ml'), null if no size options",
  "status": "Current, Limited Edition, Special Edition, Collab, or Discontinued",
  "colorways": [
    "First shade/colorway name exactly as labeled on the page",
    "Second shade/colorway name",
    "..."
  ]
}

Rules for colorways:
- Extract names exactly as labeled on the page (respect capitalization)
- If the product has no named color variants (single-version product), return ["Original"]
- Include ALL visible options — typically shown as circular swatches with text labels or a dropdown
- Do NOT list sizes or quantities as colorways
"""


def load_existing() -> dict[tuple, dict]:
    """Returns {(brand, product_line, colorway): {item_id, screenshot}}. Tries Supabase first."""
    sb = supabase_sync.load_existing()
    if sb:
        return sb
    if not VERIFIED_CSV.exists():
        return {}
    result = {}
    with open(VERIFIED_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            brand = r.get("Brand", "")
            key = (brand, r["Product Line"], r["Colorway Name"])
            result[key] = {"item_id": r["Item ID"], "screenshot": r.get("Screenshot", "No")}
    return result


def next_id_num(prefix: str) -> int:
    """Returns the next integer to use for a given ID prefix."""
    sb_num = supabase_sync.next_id_num(prefix)
    if sb_num is not None:
        return sb_num
    if not VERIFIED_CSV.exists():
        return 1
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    max_num = 0
    with open(VERIFIED_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = pattern.match(row.get("Item ID", ""))
            if m:
                max_num = max(max_num, int(m.group(1)))
    return max_num + 1


def encode_image(image_path: Path) -> tuple[str, str]:
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    }
    media_type = media_types.get(image_path.suffix.lower(), "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def screenshot_url(url: str) -> Path:
    """Take a viewport screenshot of a URL and return the temp file path."""
    import tempfile
    from playwright.sync_api import sync_playwright

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(2)  # let lazy-loaded swatches settle
            page.screenshot(path=str(tmp_path), full_page=False)  # viewport only — swatches are above fold
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Could not load {url}: {e}")
        finally:
            ctx.close()

    return tmp_path


def extract_from_page(image_path: Path, client: anthropic.Anthropic) -> dict:
    image_data, media_type = encode_image(image_path)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    response = message.content[0].text.strip()
    if response.startswith("```"):
        lines = response.splitlines()
        response = "\n".join(lines[1:-1])
    return json.loads(response)


def save_screenshot_as_reference(image_path: Path, item_id: str, brand: str, id_prefix: str) -> str:
    """
    Upload the Playwright screenshot to Supabase Storage and copy it locally.
    Returns the Supabase public URL, "Yes" (local-only), or "" on failure.
    """
    storage_path = f"{brand.lower()}/{id_prefix}/{item_id}.png"
    url = supabase_sync.upload_image(image_path, storage_path)

    # Also keep a local copy during transition
    try:
        save_dir = SCREENSHOTS_DIR / brand.lower() / id_prefix
        save_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(image_path), str(save_dir / f"{item_id}.png"))
    except Exception:
        pass

    return url or "Yes"


def append_to_csv(rows: list[dict]):
    file_exists = VERIFIED_CSV.exists()
    with open(VERIFIED_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def process_url(
    url: str,
    brand: str,
    product_line: str,
    model_name: str,
    id_prefix: str,
    existing: dict,
    client: anthropic.Anthropic,
) -> list[dict]:
    """Screenshot a product page, extract all colorways, return new CSV rows."""
    print(f"\n  {url[:80]}")

    try:
        tmp_path = screenshot_url(url)
    except RuntimeError as e:
        print(f"    FAILED (screenshot): {e}")
        return []

    try:
        extracted = extract_from_page(tmp_path, client)
    except (json.JSONDecodeError, Exception) as e:
        print(f"    FAILED (extraction): {e}")
        tmp_path.unlink(missing_ok=True)
        return []

    colorways = extracted.get("colorways") or ["Original"]
    price = extracted.get("price") or ""
    sale_price = extracted.get("sale_price") or ""
    sizes_str = extracted.get("sizes_available") or ""
    status = extracted.get("status") or "Current"

    print(f"    {len(colorways)} colorway(s): {', '.join(colorways[:5])}{'...' if len(colorways) > 5 else ''}")

    seq = next_id_num(id_prefix)
    new_rows: list[dict] = []

    for colorway in colorways:
        key = (brand, product_line, colorway)
        if key in existing:
            print(f"    skip {colorway} (already in database)")
            continue

        item_id = f"{id_prefix}-{seq:03d}"
        img_result = save_screenshot_as_reference(tmp_path, item_id, brand, id_prefix)

        row = {
            "Item ID": item_id,
            "Brand": brand,
            "Product Line": product_line,
            "Model Name": model_name,
            "Colorway Name": colorway,
            "Sizes Available": sizes_str,
            "Status": status,
            "Price": price,
            "Sale Price": sale_price,
            "Regions": "",
            "Trust Level": "5",
            "Source Type": "Official Page",
            "Source URL": url,
            "Screenshot": img_result,
            "Notes": f"Auto-scraped {datetime.now().strftime('%Y-%m-%d')}",
        }
        new_rows.append(row)
        existing[key] = {"item_id": item_id, "screenshot": img_result}
        seq += 1
        print(f"    + {item_id}  {colorway}")

    tmp_path.unlink(missing_ok=True)
    return new_rows


def main():
    parser = argparse.ArgumentParser(
        description="Extract official product data from brand website pages into Verified_Products.csv"
    )
    parser.add_argument("--brand", required=True, help="Brand name (e.g. Glossier)")
    parser.add_argument("--product-line", required=True, dest="product_line",
                        help="Product line name (e.g. 'Balm Dotcom')")
    parser.add_argument("--id-prefix", required=True, dest="id_prefix",
                        help="ID prefix for new rows (e.g. glossier-balmdotcom)")
    parser.add_argument("--urls", required=True,
                        help="Path to text file with one official product page URL per line")
    parser.add_argument("--model-name", dest="model_name",
                        help="Model name if different from --product-line")
    args = parser.parse_args()

    model_name = args.model_name or args.product_line
    urls_path = Path(args.urls)
    if not urls_path.exists():
        print(f"ERROR: URL file not found: {urls_path}")
        return

    urls = [u.strip() for u in urls_path.read_text().splitlines()
            if u.strip() and not u.startswith("#")]
    if not urls:
        print("No URLs found in file.")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return

    client = anthropic.Anthropic(api_key=api_key)
    existing = load_existing()
    all_new: list[dict] = []

    print(f"\n{args.brand} — {args.product_line}")
    print("=" * 60)
    print(f"Processing {len(urls)} URL(s)...")

    for url in urls:
        rows = process_url(url, args.brand, args.product_line, model_name,
                           args.id_prefix, existing, client)
        all_new.extend(rows)
        time.sleep(1)

    if all_new:
        append_to_csv(all_new)
        print(f"\n✓ Added {len(all_new)} new row(s) to {VERIFIED_CSV.name}")
        tab = os.environ.get("VERIFIED_PRODUCTS_TAB", "Verified_Products")
        sheets_append(tab, all_new, CSV_COLUMNS)
        for row in all_new:
            supabase_sync.upsert_product(row)
    else:
        print("\nNo new rows added (all colorways already exist or extraction failed).")


if __name__ == "__main__":
    main()
