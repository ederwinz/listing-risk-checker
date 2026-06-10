"""
Supabase integration — database upserts and Storage image uploads.

All functions are non-fatal: if SUPABASE_URL / SUPABASE_SERVICE_KEY are not set,
or if any call fails, they log a warning and return a safe fallback value so the
scrapers continue writing to CSV as before.

Public API:
    load_existing()              → {(brand, product_line, colorway): {"item_id", "screenshot"}}
    next_id_num(prefix)          → int | None  (None = Supabase not available)
    upsert_product(row)          → None
    upsert_listing(row)          → None
    update_screenshot_url(id, u) → None
    upload_image(source, path)   → str | None  (public URL or None)
"""

import os
import re
import requests as _requests
from pathlib import Path

BUCKET = "product-screenshots"

# CSV column name → Supabase DB column name
_COL_MAP = {
    "Item ID":         "item_id",
    "Brand":           "brand",
    "Product Line":    "product_line",
    "Model Name":      "model_name",
    "Colorway Name":   "colorway_name",
    "Sizes Available": "sizes_available",
    "Status":          "status",
    "Price":           "price",
    "Sale Price":      "sale_price",
    "Regions":         "regions",
    "Trust Level":     "trust_level",
    "Source Type":     "source_type",
    "Source URL":      "source_url",
    "Screenshot":      "screenshot_url",
    "Notes":           "notes",
}


def _get_client():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print(f"  [Supabase] client init failed ({e})")
        return None


def load_existing() -> dict[tuple, dict]:
    """
    Returns {(brand, product_line, colorway_name): {"item_id": ..., "screenshot": ...}}
    by querying verified_products.  Returns {} if Supabase is not configured.
    """
    client = _get_client()
    if not client:
        return {}
    try:
        resp = client.table("verified_products").select(
            "item_id, brand, product_line, colorway_name, screenshot_url"
        ).execute()
        result: dict[tuple, dict] = {}
        for r in resp.data:
            key = (r["brand"], r["product_line"], r["colorway_name"])
            result[key] = {
                "item_id": r["item_id"],
                "screenshot": r.get("screenshot_url") or "No",
            }
        return result
    except Exception as e:
        print(f"  [Supabase] load_existing failed ({e})")
        return {}


def next_id_num(prefix: str) -> int | None:
    """
    Returns the next sequential integer for a given id_prefix by querying Supabase.
    Returns None if Supabase is not available (caller falls back to CSV).
    """
    client = _get_client()
    if not client:
        return None
    try:
        resp = client.table("verified_products").select("item_id").like(
            "item_id", f"{prefix}-%"
        ).execute()
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        max_num = 0
        for r in resp.data:
            m = pattern.match(r["item_id"])
            if m:
                max_num = max(max_num, int(m.group(1)))
        return max_num + 1
    except Exception as e:
        print(f"  [Supabase] next_id_num failed ({e})")
        return None


def _to_db_row(row: dict) -> dict:
    """Convert a CSV-keyed dict to Supabase column names."""
    db: dict = {}
    for csv_key, db_col in _COL_MAP.items():
        if csv_key in row:
            val = row[csv_key]
            if db_col == "trust_level":
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    val = 5
            db[db_col] = val
    return db


def upsert_product(row: dict) -> None:
    """Upsert one verified_products row (keyed on item_id)."""
    client = _get_client()
    if not client:
        return
    try:
        client.table("verified_products").upsert(
            _to_db_row(row), on_conflict="item_id"
        ).execute()
    except Exception as e:
        print(f"  [Supabase] upsert_product failed ({e})")


def upsert_listing(row: dict) -> None:
    """Upsert one test_listings row (keyed on testing_id)."""
    client = _get_client()
    if not client:
        return
    try:
        client.table("test_listings").upsert(row, on_conflict="testing_id").execute()
    except Exception as e:
        print(f"  [Supabase] upsert_listing failed ({e})")


def update_screenshot_url(item_id: str, url: str) -> None:
    """Patch screenshot_url for an existing verified_products row."""
    client = _get_client()
    if not client:
        return
    try:
        client.table("verified_products").update(
            {"screenshot_url": url}
        ).eq("item_id", item_id).execute()
    except Exception as e:
        print(f"  [Supabase] update_screenshot_url failed ({e})")


def upload_image(source, storage_path: str) -> str | None:
    """
    Upload an image to Supabase Storage and return its public URL.

    source: URL string to download from, local Path to read, or raw bytes.
    Returns None if upload fails or Supabase is not configured.
    """
    client = _get_client()
    if not client:
        return None
    try:
        if isinstance(source, bytes):
            data = source
            ext = Path(storage_path).suffix.lower()
            content_type = "image/png" if ext == ".png" else "image/jpeg"
        elif isinstance(source, Path):
            data = source.read_bytes()
            ext = source.suffix.lower()
            content_type = "image/png" if ext == ".png" else "image/jpeg"
        else:
            resp = _requests.get(source, timeout=30)
            resp.raise_for_status()
            data = resp.content
            content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]

        client.storage.from_(BUCKET).upload(
            storage_path, data,
            {"content-type": content_type, "upsert": "true"},
        )
        return client.storage.from_(BUCKET).get_public_url(storage_path)
    except Exception as e:
        print(f"  [Supabase] upload_image failed ({e})")
        return None
