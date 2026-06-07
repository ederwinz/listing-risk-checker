#!/usr/bin/env python3
"""
Extract structured listing data from marketplace screenshots or URLs into Test_Listings.csv.

Screenshot mode (drop files into inbox/):
    python scrapers/listing_extractor.py --platform Rednote

URL mode (paste one URL per line into a text file):
    python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote

URL mode with your logged-in Chrome profile (for platforms that require login):
    python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote \\
        --user-data-dir "/Users/you/Library/Application Support/Google/Chrome/Default"

Both modes can be combined in one run.
"""

import argparse
import anthropic
import base64
import csv
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sheets_sync import append_rows as sheets_append

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
INBOX_DIR = BASE_DIR / "inbox"
PROCESSED_DIR = BASE_DIR / "processed"
TEST_LISTINGS_CSV = BASE_DIR / "Test_Listings.csv"

CSV_COLUMNS = [
    "testing_id", "platform", "seller_name", "listing_title",
    "claimed_brand", "claimed_productline", "claimed_modelname",
    "claimed_size", "claimed_colorway", "claimed_status",
    "main_colors", "expected_matchid", "notes", "risk_level",
    "expected_matchconfidence", "mismatch_reasons", "seller_claims",
    "listing_description",
]

REQUIRED_FIELDS = ["platform", "claimed_brand", "claimed_colorway", "seller_name"]

EXTRACTION_PROMPT = """You are extracting structured product listing data from a marketplace screenshot.
The listing may be from Rednote (小红书), Taobao (淘宝), Xianyu (闲鱼), or another Chinese e-commerce platform.

Extract the following fields and return ONLY a valid JSON object — no explanation, no markdown fences.
Use null for any field you cannot determine. Preserve Chinese text exactly as shown.

Platform detection hints:
- Rednote (小红书): red header bar, red logo, note/post style layout, heart icons
- Taobao (淘宝): orange branding, shopping cart icon, 淘宝 text visible
- Xianyu (闲鱼): secondhand/resale layout, 闲鱼 text, fish logo, blue/teal accents
- Tmall (天猫): black cat logo, premium store layout
- JD (京东): red JD logo

{
  "platform": "App/platform name in English (Rednote, Taobao, Xianyu, Tmall, JD, WeChat, etc.)",
  "seller_name": "Seller or shop name exactly as displayed (preserve Chinese characters)",
  "listing_title": "Core product description only — strip brand name if it duplicates claimed_brand, remove 【】brackets and marketing filler words, keep the descriptive product name in original language",
  "claimed_brand": "Brand being sold (e.g. Owala, Stanley, Lululemon) — English name",
  "claimed_productline": "Product family/line name (e.g. Freesip, Quencher, Define jacket)",
  "claimed_modelname": "The FULL verbose product name string the seller uses, often in Chinese — this is different from claimed_productline. Example: 'Freesip304双饮保温杯吸管不锈钢水杯'. Include it even if it partially overlaps with claimed_productline.",
  "claimed_size": "Size shown (e.g. 24 oz, 945 ml, 1L, 32oz)",
  "claimed_colorway": "Color or colorway name. Check ALL of these locations: (1) any 'Selected:' or '已选:' field which shows the currently chosen variant — this is the most reliable source, extract the name in parentheses if present e.g. 'Selected: 元气粉(Bunny Business)16oz' → 'Bunny Business', (2) color selector buttons or swatches with text labels, (3) product title, (4) description or SKU strings. If no official color name exists anywhere, describe the visual color from the product photo (e.g. 'light blue', 'sage green'). Only use null if the product truly has no color variant.",
  "claimed_status": "ongoing, special edition, limited edition, collab, discontinued, or unknown",
  "main_colors": "Comma-separated visual colors visible in product photos (e.g. pink, white, sage green)",
  "seller_claims": "Any special claims: official store, authentic, Japan limited, collab with X, global exclusive, etc. null if none.",
  "listing_description": "Key text from the description if visible, truncated to 200 chars"
}"""


def get_next_testing_id() -> str:
    if not TEST_LISTINGS_CSV.exists():
        return "XHS-001"
    with open(TEST_LISTINGS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        max_num = 0
        for row in reader:
            tid = row.get("testing_id", "")
            if tid.startswith("XHS-"):
                try:
                    max_num = max(max_num, int(tid.split("-")[1]))
                except ValueError:
                    pass
    return f"XHS-{max_num + 1:03d}"


def encode_image(image_path: Path) -> tuple[str, str]:
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    }
    media_type = media_types.get(image_path.suffix.lower(), "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def extract_from_screenshot(image_path: Path, client: anthropic.Anthropic) -> dict:
    image_data, media_type = encode_image(image_path)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_data},
                },
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    response = message.content[0].text.strip()
    if response.startswith("```"):
        lines = response.splitlines()
        response = "\n".join(lines[1:-1])
    return json.loads(response)


def screenshot_url(url: str, user_data_dir: str | None) -> Path:
    """Opens URL in Playwright, takes a full-page screenshot, returns path to temp PNG."""
    from playwright.sync_api import sync_playwright

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)

    with sync_playwright() as p:
        launch_kwargs = {"headless": True}
        if user_data_dir:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,  # persistent context works better headed
                viewport={"width": 390, "height": 844},  # mobile viewport for Chinese apps
            )
            page = ctx.new_page()
        else:
            browser = p.chromium.launch(**launch_kwargs)
            ctx = browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
            )
            page = ctx.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(2)  # let lazy-loaded content settle
            page.screenshot(path=str(tmp_path), full_page=True)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"Could not load {url}: {e}")
        finally:
            ctx.close()
            if user_data_dir is None:
                pass  # browser auto-closed via context manager

    return tmp_path


def verify_extraction(extracted: dict, testing_id: str) -> list[str]:
    """Returns list of warning strings for missing required fields."""
    warnings = []
    for field in REQUIRED_FIELDS:
        if not extracted.get(field):
            warnings.append(f"{field} is empty")
    return warnings


def build_row(testing_id: str, extracted: dict, platform_override: str | None, warnings: list[str]) -> dict:
    row = {col: "" for col in CSV_COLUMNS}
    row["testing_id"] = testing_id

    for field in ["platform", "seller_name", "listing_title", "claimed_brand",
                  "claimed_productline", "claimed_modelname", "claimed_size",
                  "claimed_colorway", "claimed_status", "main_colors",
                  "seller_claims", "listing_description"]:
        value = extracted.get(field)
        row[field] = value if value is not None else ""

    if platform_override:
        row["platform"] = platform_override

    if warnings:
        row["notes"] = "NEEDS REVIEW: " + "; ".join(warnings)

    return row


def append_row(row: dict):
    file_exists = TEST_LISTINGS_CSV.exists()
    with open(TEST_LISTINGS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
    tab = os.environ.get("TEST_LISTINGS_TAB", "Test_Listings")
    sheets_append(tab, [row], CSV_COLUMNS)


def process_image(image_path: Path, client: anthropic.Anthropic, platform_override: str | None,
                  move_to_processed: bool = True) -> bool:
    """Extract from a single image file and append to CSV. Returns True on success."""
    try:
        extracted = extract_from_screenshot(image_path, client)
    except json.JSONDecodeError as e:
        print(f"FAILED (bad JSON: {e})")
        return False
    except Exception as e:
        print(f"FAILED ({e})")
        return False

    testing_id = get_next_testing_id()
    warnings = verify_extraction(extracted, testing_id)
    row = build_row(testing_id, extracted, platform_override, warnings)
    append_row(row)

    if move_to_processed:
        date_folder = PROCESSED_DIR / datetime.now().strftime("%Y-%m-%d")
        date_folder.mkdir(exist_ok=True)
        shutil.move(str(image_path), str(date_folder / image_path.name))

    brand = row.get("claimed_brand") or ""
    colorway = row.get("claimed_colorway") or ""
    status = " ⚠ " + "; ".join(warnings) if warnings else ""
    print(f"→ {testing_id}  {brand} / {colorway}{status}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Extract marketplace listing data into Test_Listings.csv")
    parser.add_argument("--platform", help="Override platform detection (e.g. Rednote, Taobao, Xianyu)")
    parser.add_argument("--urls", help="Path to a text file with one listing URL per line")
    parser.add_argument("--user-data-dir", help="Chrome profile directory for logged-in sessions")
    args = parser.parse_args()

    INBOX_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(exist_ok=True)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        return

    client = anthropic.Anthropic(api_key=api_key)
    total = added = 0

    # --- Screenshot mode: process inbox/ ---
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    images = sorted(p for p in INBOX_DIR.iterdir() if p.suffix.lower() in image_extensions)

    if images:
        print(f"Screenshot mode: {len(images)} image(s) in inbox/")
        for image_path in images:
            print(f"  {image_path.name} ...", end=" ", flush=True)
            total += 1
            if process_image(image_path, client, args.platform):
                added += 1

    # --- URL mode: screenshot each URL then extract ---
    if args.urls:
        urls_path = Path(args.urls)
        if not urls_path.exists():
            print(f"ERROR: URL file not found: {urls_path}")
        else:
            urls = [u.strip() for u in urls_path.read_text().splitlines() if u.strip() and not u.startswith("#")]
            print(f"\nURL mode: {len(urls)} URL(s) from {urls_path.name}")
            for url in urls:
                print(f"  {url[:60]}... ", end=" ", flush=True)
                total += 1
                try:
                    tmp_path = screenshot_url(url, args.user_data_dir)
                except RuntimeError as e:
                    print(f"FAILED ({e})")
                    continue

                success = process_image(tmp_path, client, args.platform, move_to_processed=False)
                if success:
                    # Save the auto-screenshot for reference
                    date_folder = PROCESSED_DIR / datetime.now().strftime("%Y-%m-%d") / "url-captures"
                    date_folder.mkdir(parents=True, exist_ok=True)
                    safe_name = url.split("/")[-1][:40].replace("?", "_") or "capture"
                    dest = date_folder / f"{safe_name}.png"
                    shutil.move(str(tmp_path), str(dest))
                    added += 1
                else:
                    tmp_path.unlink(missing_ok=True)

                time.sleep(1)  # polite delay between requests

    if total == 0:
        print("Nothing to process. Drop screenshots in inbox/ or pass --urls <file>.")
    else:
        print(f"\nDone. {added}/{total} processed → Test_Listings.csv")


if __name__ == "__main__":
    main()
