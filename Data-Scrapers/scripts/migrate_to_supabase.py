#!/usr/bin/env python3
"""
One-time migration: uploads existing CSV data and local images to Supabase.

Run once after creating the Supabase tables and Storage bucket:
    cd Data-Scrapers
    python scripts/migrate_to_supabase.py

Steps:
  1. Upsert all rows from Verified_Products.csv → verified_products table
  2. Upsert all rows from Test_Listings.csv → test_listings table
  3. Upload all images from Product Screenshots/ → Supabase Storage
  4. Update screenshot_url for each uploaded image
"""

import csv
import sys
from pathlib import Path

# Add scrapers/ to path so we can import supabase_sync
sys.path.insert(0, str(Path(__file__).parent.parent / "scrapers"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import supabase_sync

BASE_DIR = Path(__file__).parent.parent
VERIFIED_CSV = BASE_DIR / "Verified_Products.csv"
TEST_CSV = BASE_DIR / "Test_Listings.csv"
SCREENSHOTS_DIR = BASE_DIR.parent / "Product Screenshots"

BATCH_SIZE = 100


def migrate_verified_products():
    if not VERIFIED_CSV.exists():
        print("  Verified_Products.csv not found — skipping.")
        return

    rows = list(csv.DictReader(open(VERIFIED_CSV, newline="", encoding="utf-8")))
    print(f"  Upserting {len(rows)} verified_products rows (batch size {BATCH_SIZE})...")

    client = supabase_sync._get_client()
    if not client:
        print("  ERROR: Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.")
        return

    ok = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        db_batch = [supabase_sync._to_db_row(r) for r in batch]
        try:
            client.table("verified_products").upsert(db_batch, on_conflict="item_id").execute()
            ok += len(batch)
            print(f"    {ok}/{len(rows)}", end="\r")
        except Exception as e:
            print(f"\n  WARN: batch {i//BATCH_SIZE + 1} failed ({e})")

    print(f"\n  ✓ {ok} rows upserted to verified_products")


def migrate_test_listings():
    if not TEST_CSV.exists():
        print("  Test_Listings.csv not found — skipping.")
        return

    rows = list(csv.DictReader(open(TEST_CSV, newline="", encoding="utf-8")))
    print(f"  Upserting {len(rows)} test_listings rows...")

    client = supabase_sync._get_client()
    if not client:
        return

    ok = 0
    for i in range(0, len(rows), BATCH_SIZE):
        # Strip any None keys that come from blank CSV header cells
        batch = [{k: v for k, v in r.items() if k is not None} for r in rows[i : i + BATCH_SIZE]]
        try:
            client.table("test_listings").upsert(batch, on_conflict="testing_id").execute()
            ok += len(batch)
        except Exception as e:
            print(f"  WARN: batch {i//BATCH_SIZE + 1} failed ({e})")

    print(f"  ✓ {ok} rows upserted to test_listings")


def migrate_images():
    if not SCREENSHOTS_DIR.exists():
        print("  Product Screenshots/ not found — skipping.")
        return

    image_files = [
        p for p in SCREENSHOTS_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
    ]
    print(f"  Uploading {len(image_files)} images to Supabase Storage...")

    uploaded = 0
    failed = 0

    for img_path in image_files:
        # Derive storage path from relative path under Product Screenshots/
        rel = img_path.relative_to(SCREENSHOTS_DIR)
        storage_path = str(rel).replace("\\", "/")  # normalize on Windows
        item_id = img_path.stem  # filename without extension

        url = supabase_sync.upload_image(img_path, storage_path)
        if url:
            supabase_sync.update_screenshot_url(item_id, url)
            uploaded += 1
        else:
            failed += 1

        if (uploaded + failed) % 50 == 0:
            print(f"    {uploaded + failed}/{len(image_files)} processed ({failed} failed)", end="\r")

    print(f"\n  ✓ {uploaded} images uploaded, {failed} failed")


def main():
    print("\n=== Supabase Migration ===\n")

    print("Step 1: verified_products")
    migrate_verified_products()

    print("\nStep 2: test_listings")
    migrate_test_listings()

    print("\nStep 3: images")
    migrate_images()

    print("\n=== Done ===")
    print("Check your Supabase dashboard to verify row counts and image URLs.")


if __name__ == "__main__":
    main()
