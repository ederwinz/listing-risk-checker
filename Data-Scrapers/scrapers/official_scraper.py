#!/usr/bin/env python3
"""
Scrapes official product data from brand Shopify stores and appends new entries
to Verified_Products.csv.  Supports multiple brands via the BRANDS config below.

Run this periodically to pick up new colorways/shades. Already-present items are
skipped (deduplication by Brand + Product Line + Colorway Name).  Any existing row
with Screenshot="No" will have its product image downloaded automatically.

Usage:
    cd Data-Scrapers
    python scrapers/official_scraper.py              # all brands
    python scrapers/official_scraper.py --brand Rhode   # Rhode only
    python scrapers/official_scraper.py --brand Owala   # Owala only
"""

import argparse
import csv
import os
import re
import sys
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sheets_sync import append_rows as sheets_append

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
VERIFIED_CSV = BASE_DIR / "Verified_Products.csv"
SCREENSHOTS_DIR = BASE_DIR.parent / "Product Screenshots"

CSV_COLUMNS = [
    "Item ID", "Brand", "Product Line", "Model Name", "Colorway Name",
    "Sizes Available", "Status", "Price", "Sale Price", "Regions",
    "Trust Level", "Source Type", "Source URL", "Screenshot", "Notes",
]

# ── Brand & Collection Config ──────────────────────────────────────────────────
#
# variant_strategy options:
#   "by_color_option"  (default) — each Shopify product has multiple color variants;
#                                  one CSV row per color variant (used for Owala)
#   "by_product_title"           — each Shopify product IS one shade/colorway;
#                                  shade extracted from product title (used for Rhode)

BRANDS = [
    {
        "brand": "Owala",
        "collections": [
            {
                "url": "https://owala.myshopify.com/collections/freesip/products.json",
                "product_line": "Freesip",
                "model_name": "Freesip",
                "id_prefix": "owala-fs",
            },
            {
                "url": "https://owala.myshopify.com/collections/kids-freesip/products.json",
                "product_line": "Kids' Freesip",
                "model_name": "Kids' Freesip",
                "id_prefix": "owala-kidsfs",
            },
            {
                "url": "https://owala.myshopify.com/collections/freesip-tumbler/products.json",
                "product_line": "Freesip Tumbler",
                "model_name": "Freesip Tumbler",
                "id_prefix": "owala-fstumbler",
            },
            {
                "url": "https://owala.myshopify.com/collections/freesip-tumbler-sway/products.json",
                "product_line": "Freesip Sway",
                "model_name": "Freesip Sway",
                "id_prefix": "owala-sway",
                "title_contains": "Sway",
            },
            {
                "url": "https://owala.myshopify.com/collections/kids-products/products.json",
                "product_line": "Kids' Tumbler",
                "model_name": "Kids' Tumbler",
                "id_prefix": "owala-kidstumbler",
                "title_contains": "Tumbler",
            },
            {
                "url": "https://owala.myshopify.com/collections/smoothsip-coffee-mugs/products.json",
                "product_line": "SmoothSip",
                "model_name": "SmoothSip",
                "id_prefix": "owala-smoothsip",
            },
        ],
    },
    {
        "brand": "Rhode",
        "collections": [
            # Two lip-tint collections overlap; deduplication handles it
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-tint/products.json",
                "product_line": "Peptide Lip Tint",
                "model_name": "Peptide Lip Tint",
                "id_prefix": "rhode-liptint",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-tint-core/products.json",
                "product_line": "Peptide Lip Tint",
                "model_name": "Peptide Lip Tint",
                "id_prefix": "rhode-liptint",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/pocket-blush/products.json",
                "product_line": "Pocket Blush",
                "model_name": "Pocket Blush",
                "id_prefix": "rhode-blush",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/pocket-bronze/products.json",
                "product_line": "Pocket Bronze",
                "model_name": "Pocket Bronze",
                "id_prefix": "rhode-bronze",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-treatment/products.json",
                "product_line": "Peptide Lip Treatment",
                "model_name": "Peptide Lip Treatment",
                "id_prefix": "rhode-liptreat",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-shape/products.json",
                "product_line": "Peptide Lip Shape",
                "model_name": "Peptide Lip Shape",
                "id_prefix": "rhode-lipshape",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/glazing-milk/products.json",
                "product_line": "Glazing Milk",
                "model_name": "Glazing Milk",
                "id_prefix": "rhode-glazingmilk",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/barrier-butter/products.json",
                "product_line": "Barrier Butter",
                "model_name": "Barrier Butter",
                "id_prefix": "rhode-barrierbutter",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/spotwear/products.json",
                "product_line": "Spotwear",
                "model_name": "Spotwear",
                "id_prefix": "rhode-spotwear",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/highlight-milk/products.json",
                "product_line": "Highlight Milk",
                "model_name": "Highlight Milk",
                "id_prefix": "rhode-highlightmilk",
                "variant_strategy": "by_product_title",
            },
        ],
    },
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; brand-reference-scraper/2.0)"}


# ── Existing data ──────────────────────────────────────────────────────────────

def load_existing() -> dict[tuple, dict]:
    """
    Returns {(brand, product_line, colorway): {"item_id": ..., "screenshot": ...}}
    for every row already in the CSV.  Used for deduplication and backfill tracking.
    """
    if not VERIFIED_CSV.exists():
        return {}
    result = {}
    with open(VERIFIED_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            brand = r.get("Brand", "Owala")
            key = (brand, r["Product Line"], r["Colorway Name"])
            result[key] = {
                "item_id": r["Item ID"],
                "screenshot": r.get("Screenshot", "No"),
            }
    return result


def next_id_num(prefix: str) -> int:
    """Returns the next integer to use for a given ID prefix."""
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


# ── Shopify API ────────────────────────────────────────────────────────────────

def fetch_products(url: str) -> list[dict]:
    resp = requests.get(url, headers=HEADERS, timeout=30, params={"limit": 250})
    resp.raise_for_status()
    return resp.json().get("products", [])


def option_key_for(options: list[dict], names: list[str]) -> str | None:
    for i, opt in enumerate(options):
        if opt["name"].lower() in names:
            return f"option{i + 1}"
    return None


def strip_units(size_str: str) -> str:
    """Remove trailing oz/ml units from purely numeric sizes. '32 oz' → '32'."""
    return re.sub(r"\s*(oz|ml|l)\b", "", size_str, flags=re.IGNORECASE).strip()


# ── Strategy: by_color_option (Owala) ─────────────────────────────────────────

def group_variants_by_colorway(products: list[dict], title_filter: str = "") -> dict[str, dict]:
    """
    Returns {colorway_name: {sizes, price, sale_price, image_url, product_url}}.
    Each color variant within a product → one row.  Used for Owala-style products.
    """
    colorways: dict[str, dict] = {}

    for product in products:
        if title_filter and title_filter.lower() not in product.get("title", "").lower():
            continue

        options = product.get("options", [])
        color_key = option_key_for(options, ["color", "colour", "colorway"])
        size_key = option_key_for(options, ["size", "capacity", "volume"])

        images_by_variant: dict[int, str] = {}
        for img in product.get("images", []):
            for vid in img.get("variant_ids", []):
                images_by_variant[vid] = img["src"]
        default_image = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://owala.com/products/{product['handle']}"

        for variant in product.get("variants", []):
            colorway = (variant.get(color_key) or "").strip() if color_key else ""
            size_raw = (variant.get(size_key) or "").strip() if size_key else ""
            size = strip_units(size_raw)
            image_url = images_by_variant.get(variant["id"], default_image)

            current_price = variant.get("price") or "0"
            compare_price = variant.get("compare_at_price")
            if compare_price and float(compare_price) > float(current_price):
                price = f"${compare_price}"
                sale_price = f"${current_price}"
            else:
                price = f"${current_price}"
                sale_price = ""

            if not colorway:
                colorway = variant.get("title", "").split("/")[0].strip()
            if not colorway:
                continue

            if colorway not in colorways:
                colorways[colorway] = {
                    "sizes": [],
                    "price": price,
                    "sale_price": sale_price,
                    "image_url": image_url,
                    "product_url": product_url,
                }
            if size and size not in colorways[colorway]["sizes"]:
                colorways[colorway]["sizes"].append(size)

    def size_sort_key(s: str) -> float:
        m = re.match(r"[\d.]+", s)
        return float(m.group()) if m else 0

    for data in colorways.values():
        data["sizes"].sort(key=size_sort_key)

    return colorways


# ── Strategy: by_product_title (Rhode) ────────────────────────────────────────

def group_products_as_colorways(products: list[dict], model_name: str) -> dict[str, dict]:
    """
    Returns {shade_name: {sizes, price, sale_price, image_url, product_url}}.
    Each Shopify product = one shade.  Shade extracted by stripping model_name prefix
    from the product title.  Products with no shade (skincare etc.) use "Original".
    Used for Rhode-style products.
    """
    colorways: dict[str, dict] = {}
    prefix = model_name.lower().strip()

    for product in products:
        title = product.get("title", "").lower().strip()
        shade = title.removeprefix(prefix).strip().title() or "Original"

        opts = product.get("options", [])
        size_key = option_key_for(opts, ["size", "capacity", "volume"])
        sizes: list[str] = []
        for v in product.get("variants", []):
            if size_key:
                sz = (v.get(size_key) or "").strip()
                if sz and sz != "Default Title" and sz not in sizes:
                    sizes.append(sz)

        variants = product.get("variants", [])
        price, sale_price = "$0", ""
        if variants:
            v = variants[0]
            current = v.get("price") or "0"
            compare = v.get("compare_at_price")
            if compare and float(compare) > float(current):
                price, sale_price = f"${compare}", f"${current}"
            else:
                price = f"${current}"

        image_url = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://rhodeskin.com/products/{product['handle']}"

        if shade not in colorways:
            colorways[shade] = {
                "sizes": sizes,
                "price": price,
                "sale_price": sale_price,
                "image_url": image_url,
                "product_url": product_url,
            }

    return colorways


# ── Image download ─────────────────────────────────────────────────────────────

def save_product_image(item_id: str, brand: str, id_prefix: str, image_url: str) -> bool:
    """Download a Shopify product image and save under Product Screenshots/."""
    if not image_url:
        return False
    ext = Path(image_url.split("?")[0]).suffix or ".jpg"
    save_dir = SCREENSHOTS_DIR / brand.lower() / id_prefix
    save_dir.mkdir(parents=True, exist_ok=True)
    dest = save_dir / f"{item_id}{ext}"
    try:
        resp = requests.get(image_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"    [img] {e}")
        return False


# ── Scraping ───────────────────────────────────────────────────────────────────

def scrape_collection(
    config: dict,
    brand: str,
    existing: dict[tuple, dict],
    updated_screenshots: dict[str, str],
) -> list[dict]:
    """
    Scrape one collection config entry.  Returns list of new rows to append.
    Also mutates `updated_screenshots` with item_ids whose Screenshot field changed.
    """
    print(f"\n  [{config['product_line']}]  {config['url']}")
    try:
        products = fetch_products(config["url"])
    except requests.HTTPError as e:
        print(f"    HTTP {e.response.status_code} — collection URL may have changed, skipping.")
        return []
    except requests.ConnectionError as e:
        print(f"    Connection failed — check VPN / network and retry.")
        return []

    strategy = config.get("variant_strategy", "by_color_option")
    if strategy == "by_product_title":
        colorways = group_products_as_colorways(products, config["model_name"])
    else:
        title_filter = config.get("title_contains", "")
        colorways = group_variants_by_colorway(products, title_filter)

    seq = next_id_num(config["id_prefix"])
    new_rows: list[dict] = []

    for colorway, data in colorways.items():
        key = (brand, config["product_line"], colorway)

        if key in existing:
            info = existing[key]
            if info["screenshot"] == "No" and data.get("image_url"):
                ok = save_product_image(
                    info["item_id"], brand, config["id_prefix"], data["image_url"]
                )
                if ok:
                    updated_screenshots[info["item_id"]] = "Yes"
                    print(f"    img  {info['item_id']}  {colorway}")
            else:
                print(f"    skip {colorway}")
            continue

        item_id = f"{config['id_prefix']}-{seq:03d}"
        sizes_str = ", ".join(data["sizes"])
        sale_label = f" → sale {data['sale_price']}" if data["sale_price"] else ""

        img_ok = save_product_image(item_id, brand, config["id_prefix"], data["image_url"])

        row = {
            "Item ID": item_id,
            "Brand": brand,
            "Product Line": config["product_line"],
            "Model Name": config["model_name"],
            "Colorway Name": colorway,
            "Sizes Available": sizes_str,
            "Status": "Current",
            "Price": data["price"],
            "Sale Price": data["sale_price"],
            "Regions": "",
            "Trust Level": "5",
            "Source Type": "Official Page",
            "Source URL": data["product_url"],
            "Screenshot": "Yes" if img_ok else "No",
            "Notes": f"Auto-scraped {datetime.now().strftime('%Y-%m-%d')}",
        }
        new_rows.append(row)
        existing[key] = {"item_id": item_id, "screenshot": row["Screenshot"]}
        seq += 1
        print(f"    +  {item_id}  {colorway}  ({sizes_str})  {data['price']}{sale_label}"
              + ("  [img]" if img_ok else ""))

    return new_rows


# ── CSV I/O ────────────────────────────────────────────────────────────────────

def append_to_csv(rows: list[dict]):
    file_exists = VERIFIED_CSV.exists()
    with open(VERIFIED_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def rewrite_csv_with_screenshot_updates(updates: dict[str, str]):
    """Flush in-place Screenshot="Yes" updates back to the CSV."""
    rows = list(csv.DictReader(open(VERIFIED_CSV, newline="", encoding="utf-8")))
    for row in rows:
        if row["Item ID"] in updates:
            row["Screenshot"] = updates[row["Item ID"]]
    with open(VERIFIED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape official product data into Verified_Products.csv")
    parser.add_argument("--brand", help="Only scrape this brand (e.g. Owala, Rhode)")
    args = parser.parse_args()

    existing = load_existing()
    updated_screenshots: dict[str, str] = {}
    all_new: list[dict] = []

    brands_to_run = [
        b for b in BRANDS
        if not args.brand or b["brand"].lower() == args.brand.lower()
    ]
    if not brands_to_run:
        print(f"Unknown brand '{args.brand}'. Available: {[b['brand'] for b in BRANDS]}")
        return

    for brand_config in brands_to_run:
        brand = brand_config["brand"]
        print(f"\n{'='*60}\n{brand}\n{'='*60}")
        for col_config in brand_config["collections"]:
            rows = scrape_collection(col_config, brand, existing, updated_screenshots)
            all_new.extend(rows)

    if all_new:
        append_to_csv(all_new)
        print(f"\n✓ Added {len(all_new)} new row(s) to {VERIFIED_CSV.name}")
        tab = os.environ.get("VERIFIED_PRODUCTS_TAB", "Verified_Products")
        sheets_append(tab, all_new, CSV_COLUMNS)

    if updated_screenshots:
        rewrite_csv_with_screenshot_updates(updated_screenshots)
        print(f"✓ Backfilled images for {len(updated_screenshots)} existing row(s)")

    if not all_new and not updated_screenshots:
        print("\nNo new products and no missing images — database is up to date.")


if __name__ == "__main__":
    main()
