#!/usr/bin/env python3
"""
Migration: upserts CSV data to Supabase. Safe to re-run — skips already-migrated rows.

Steps:
  1. Upsert new rows from Verified_Products.csv → verified_products table
  2. Upsert new rows from Test_Listings.csv → test_listings table
  3. Print verification summary comparing CSV vs Supabase counts

Note: image URLs are now Shopify CDN URLs stored directly in screenshot_url.
No image downloading or Supabase Storage upload is needed.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scrapers"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import supabase_sync

BASE_DIR = Path(__file__).parent.parent
VERIFIED_CSV = BASE_DIR / "Verified_Products.csv"
TEST_CSV = BASE_DIR / "Test_Listings.csv"

BATCH_SIZE = 100


def _fetch_existing_ids(client, table: str, id_col: str) -> set:
    """Fetch all existing IDs from a Supabase table, handles >1000 rows."""
    ids: set = set()
    page_size = 1000
    offset = 0
    while True:
        try:
            resp = (
                client.table(table)
                .select(id_col)
                .range(offset, offset + page_size - 1)
                .execute()
            )
        except Exception as e:
            print(f"  WARN: could not fetch existing {table} IDs ({e})")
            break
        if not resp.data:
            break
        ids.update(r[id_col] for r in resp.data)
        if len(resp.data) < page_size:
            break
        offset += page_size
    return ids


def migrate_verified_products():
    if not VERIFIED_CSV.exists():
        print("  Verified_Products.csv not found — skipping.")
        return

    rows = list(csv.DictReader(open(VERIFIED_CSV, newline="", encoding="utf-8")))

    client = supabase_sync._get_client()
    if not client:
        print("  ERROR: Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.")
        return

    existing_ids = _fetch_existing_ids(client, "verified_products", "item_id")
    new_rows = [r for r in rows if r.get("Item ID") not in existing_ids]
    print(f"  {len(existing_ids)} already in Supabase, {len(new_rows)} new rows to upsert...")

    if not new_rows:
        print("  ✓ Nothing to do — all rows already migrated.")
        return

    ok = 0
    skipped = 0
    for i in range(0, len(new_rows), BATCH_SIZE):
        batch = new_rows[i : i + BATCH_SIZE]
        db_batch = [supabase_sync._to_db_row(r) for r in batch]
        try:
            client.table("verified_products").upsert(db_batch, on_conflict="item_id").execute()
            ok += len(batch)
            print(f"    {ok}/{len(new_rows)}", end="\r")
        except Exception:
            for row_data in db_batch:
                try:
                    client.table("verified_products").upsert(row_data, on_conflict="item_id").execute()
                    ok += 1
                except Exception as e2:
                    skipped += 1
                    print(f"\n  SKIP {row_data.get('item_id')}: {e2}")

    print(f"\n  ✓ {ok} rows upserted to verified_products" + (f", {skipped} skipped (duplicate key)" if skipped else ""))


def migrate_test_listings():
    if not TEST_CSV.exists():
        print("  Test_Listings.csv not found — skipping.")
        return

    rows = list(csv.DictReader(open(TEST_CSV, newline="", encoding="utf-8")))

    client = supabase_sync._get_client()
    if not client:
        return

    existing_ids = _fetch_existing_ids(client, "test_listings", "testing_id")
    new_rows = [r for r in rows if r.get("testing_id") not in existing_ids]
    print(f"  {len(existing_ids)} already in Supabase, {len(new_rows)} new rows to upsert...")

    if not new_rows:
        print("  ✓ Nothing to do — all rows already migrated.")
        return

    ok = 0
    for i in range(0, len(new_rows), BATCH_SIZE):
        batch = [{k: v for k, v in r.items() if k is not None} for r in new_rows[i : i + BATCH_SIZE]]
        try:
            client.table("test_listings").upsert(batch, on_conflict="testing_id").execute()
            ok += len(batch)
        except Exception as e:
            print(f"  WARN: batch {i//BATCH_SIZE + 1} failed ({e})")

    print(f"  ✓ {ok} rows upserted to test_listings")


def verify():
    client = supabase_sync._get_client()
    if not client:
        return

    vp_csv = sum(1 for _ in csv.DictReader(open(VERIFIED_CSV, newline="", encoding="utf-8")))
    tl_csv = sum(1 for _ in csv.DictReader(open(TEST_CSV, newline="", encoding="utf-8"))) if TEST_CSV.exists() else 0
    vp_db = len(_fetch_existing_ids(client, "verified_products", "item_id"))
    tl_db = len(_fetch_existing_ids(client, "test_listings", "testing_id"))

    img_with_url = 0
    offset = 0
    while True:
        try:
            resp = (
                client.table("verified_products")
                .select("screenshot_url")
                .range(offset, offset + 999)
                .execute()
            )
        except Exception:
            break
        if not resp.data:
            break
        img_with_url += sum(1 for r in resp.data if (r.get("screenshot_url") or "").startswith("https://"))
        if len(resp.data) < 1000:
            break
        offset += 1000

    vp_ok = "✓" if vp_db >= vp_csv else f"✗  MISSING {vp_csv - vp_db} rows"
    tl_ok = "✓" if tl_db >= tl_csv else f"✗  MISSING {tl_csv - tl_db} rows"
    img_ok = "✓" if img_with_url >= vp_csv else f"✗  MISSING URLs for {vp_csv - img_with_url} rows"

    print("\n=== Verification ===")
    print(f"  verified_products : CSV {vp_csv}  |  Supabase {vp_db}  {vp_ok}")
    print(f"  test_listings     : CSV {tl_csv}   |  Supabase {tl_db}  {tl_ok}")
    print(f"  images with URL   : {img_with_url} / {vp_csv}  {img_ok}")


def main():
    print("\n=== Supabase Migration (incremental) ===\n")

    print("Step 1: verified_products")
    migrate_verified_products()

    print("\nStep 2: test_listings")
    migrate_test_listings()

    verify()


if __name__ == "__main__":
    main()
