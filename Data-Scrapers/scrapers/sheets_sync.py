"""
Shared Google Sheets sync utility.

Both official_scraper.py and listing_extractor.py call append_rows() after
writing to their local CSV to keep the Google Sheet in sync.

Setup (one-time):
1. Go to console.cloud.google.com
2. Create a project → enable "Google Sheets API" and "Google Drive API"
3. IAM & Admin → Service Accounts → Create service account → Create key (JSON)
4. Save the downloaded JSON file as Data-Scrapers/google-credentials.json
5. Open your Google Sheet → Share → paste the service account email → Editor

Required .env keys:
    GOOGLE_CREDENTIALS_PATH=google-credentials.json
    GOOGLE_SHEET_ID=15zxBq4slqjCM2ZQthFVzyKciJwl0ko10RnLb13z_7q4
    VERIFIED_PRODUCTS_TAB=Verified_Products
    TEST_LISTINGS_TAB=Test_Listings
"""

import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent

_client_cache = None


def _get_client():
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        raise RuntimeError("Google Sheets dependencies not installed. Run: pip install -r requirements.txt")

    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "google-credentials.json")
    full_path = BASE_DIR / creds_path
    if not full_path.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {full_path}\n"
            "See setup instructions at the top of scrapers/sheets_sync.py"
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(str(full_path), scopes=scopes)
    _client_cache = gspread.authorize(creds)
    return _client_cache


def append_rows(tab_name: str, rows: list[dict], columns: list[str],
                sheet_id: Optional[str] = None) -> bool:
    """
    Append rows to a named tab in the Google Sheet.
    Returns True on success, False on failure (with a printed warning).
    Always non-fatal — CSV is the source of truth.
    """
    if not rows:
        return True

    resolved_sheet_id = sheet_id or os.environ.get("GOOGLE_SHEET_ID")
    if not resolved_sheet_id:
        print("  [Sheets] Skipping — GOOGLE_SHEET_ID not set in .env")
        return False

    try:
        client = _get_client()
        sheet = client.open_by_key(resolved_sheet_id)

        try:
            worksheet = sheet.worksheet(tab_name)
        except Exception:
            # Tab doesn't exist yet — create it
            worksheet = sheet.add_worksheet(title=tab_name, rows=1000, cols=len(columns))

        # Write header if sheet is empty
        existing = worksheet.get_all_values()
        if not existing:
            worksheet.append_row(columns, value_input_option="RAW")
            existing = [columns]

        # Expand sheet if needed before writing
        next_row = len(existing) + 1
        required_rows = next_row + len(rows) - 1
        if worksheet.row_count < required_rows:
            worksheet.add_rows(required_rows - worksheet.row_count + 100)

        # Write immediately after the last row that has data (ignores blank rows below)
        data = [[str(row.get(col, "")) for col in columns] for row in rows]
        worksheet.update(f"A{next_row}", data, value_input_option="RAW")
        print(f"  [Sheets] Synced {len(rows)} row(s) → '{tab_name}' tab")
        return True

    except FileNotFoundError as e:
        print(f"  [Sheets] Skipping — {e}")
        return False
    except RuntimeError as e:
        print(f"  [Sheets] Skipping — {e}")
        return False
    except Exception as e:
        print(f"  [Sheets] WARNING: sync failed ({e}) — CSV is still up to date")
        return False
