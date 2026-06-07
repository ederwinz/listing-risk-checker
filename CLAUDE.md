# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the data pipeline for a **listing risk checker** — an app that helps buyers in China verify whether overseas products sold on platforms like Rednote, Taobao, and Xianyu match official brand references. The output is a mismatch risk score, not a "fake/real" verdict (for legal reasons). The current MVP focuses on Owala drinkware.

The product is positioned as an **official-reference mismatch checker**, not an "AI fake detector."

## Running the Scrapers

All commands run from `Data-Scrapers/`:

```bash
# Scrape all brands (Owala + Rhode)
python scrapers/official_scraper.py

# Scrape one brand only
python scrapers/official_scraper.py --brand Rhode
python scrapers/official_scraper.py --brand Owala

# Extract listings from screenshots dropped in inbox/
python scrapers/listing_extractor.py --platform Rednote

# Extract listings from a text file of URLs (one per line)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote

# URL mode with a logged-in Chrome profile (needed for platforms that require login)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote \
  --user-data-dir "/Users/you/Library/Application Support/Google/Chrome/Default"

# Force full re-sync of Verified_Products.csv → Google Sheets (run after manual edits or sheet corruption)
python3 -c "
import sys, csv, os; sys.path.insert(0, 'scrapers')
from dotenv import load_dotenv; load_dotenv('.env')
from sheets_sync import _get_client
cols = ['Item ID','Product Line','Model Name','Colorway Name','Sizes Available','Status','Price','Sale Price','Regions','Trust Level','Source Type','Source URL','Screenshot','Notes']
rows = list(csv.DictReader(open('Verified_Products.csv', newline='', encoding='utf-8')))
client = _get_client(); sheet = client.open_by_key(os.environ['GOOGLE_SHEET_ID'])
ws = sheet.worksheet(os.environ.get('VERIFIED_PRODUCTS_TAB','Verified_Products'))
ws.clear()
data = [cols] + [[str(r.get(c,'')) for c in cols] for r in rows]
if ws.row_count < len(data) + 10: ws.add_rows(len(data) + 10 - ws.row_count)
ws.update(values=data, range_name='A1', value_input_option='RAW')
print(f'Synced {len(rows)} rows.')
"
```

## Environment Setup

```bash
pip install -r Data-Scrapers/requirements.txt
playwright install chromium   # only needed for URL mode
```

Required `Data-Scrapers/.env` keys:
```
ANTHROPIC_API_KEY=...
GOOGLE_CREDENTIALS_PATH=google-credentials.json
GOOGLE_SHEET_ID=15zxBq4slqjCM2ZQthFVzyKciJwl0ko10RnLb13z_7q4
VERIFIED_PRODUCTS_TAB=Verified_Products
TEST_LISTINGS_TAB=Test_Listings
```

`Data-Scrapers/google-credentials.json` must be a Google service account key with Editor access to the Google Sheet. Google Sheets sync is non-fatal — if credentials are missing, scrapers still write to local CSV.

## Architecture

### Data Flow

```
Official sources (owala.myshopify.com Shopify JSON API)
    → official_scraper.py
    → Verified_Products.csv + Google Sheets "Verified_Products" tab

Chinese marketplace screenshots / URLs
    → listing_extractor.py (Claude Haiku vision)
    → Test_Listings.csv + Google Sheets "Test_Listings" tab
```

### Two Databases

**`Verified_Products.csv`** — ground truth of what officially exists. Schema:
`Item ID, Brand, Product Line, Model Name, Colorway Name, Sizes Available, Status, Price, Sale Price, Regions, Trust Level, Source Type, Source URL, Screenshot, Notes`

- `Brand`: "Owala", "Rhode", etc.
- `Trust Level`: 5 = official brand site, 4 = authorized retailer
- `Price`: original/MSRP price (compare_at_price from Shopify when available)
- `Sale Price`: current discounted price, blank if no discount
- `Sizes Available`: bare numbers for Owala (e.g. `24, 32, 40`); descriptive labels for Rhode skincare (e.g. `big (4.2 oz), little (1.7 oz)`)
- `Regions`: intentionally left blank for all rows (reserved for future use)
- `Screenshot`: "Yes" if a product image was downloaded to `Product Screenshots/`; "No" rows are auto-retried on the next scraper run
- Deduplication key is `(Brand, Product Line, Colorway Name)` — the scraper skips any triple already present

**Owala Item ID prefixes:** `owala-fs`, `owala-kidsfs`, `owala-fstumbler`, `owala-fstwist`, `owala-sway`, `owala-kidstumbler`, `owala-smoothsip`

**Rhode Item ID prefixes:** `rhode-liptint`, `rhode-blush`, `rhode-bronze`, `rhode-liptreat`, `rhode-lipshape`, `rhode-glazingmilk`, `rhode-barrierbutter`, `rhode-spotwear`, `rhode-highlightmilk`

**Caveat on manually-entered rows:** The early manual entries for Kids' Freesip (`owala-kidsfs-*`) and FreeSip Tumbler (`owala-fstumbler-*`) have `Product Line = "Freesip"` instead of their correct product line names. This is intentional legacy data. As a side-effect, colorways shared between Freesip and Kids' Freesip (e.g. "Read My Lips") appear as duplicates in the CSV — this is expected and harmless for the reference database.

**`Test_Listings.csv`** — marketplace listings for testing the comparison engine. Testing IDs follow `XHS-NNN`. Rows with `NEEDS REVIEW:` in `notes` have missing required fields and need manual inspection.

### Key Files

- `scrapers/official_scraper.py` — multi-brand Shopify JSON API scraper. `BRANDS` list at the top configures each brand and its collections. Supports two variant strategies: `"by_color_option"` (Owala — each product has color variants) and `"by_product_title"` (Rhode — each product IS one shade, name extracted from title). Automatically downloads product images on scrape; rows with `Screenshot="No"` are retried on next run. Uses `owala.myshopify.com` for Owala (not `owala.com` — geo-blocked from some networks) and `rhodeskin.myshopify.com` for Rhode. Each Owala collection entry supports an optional `title_contains` filter to extract one product type from a mixed collection.
- `scrapers/listing_extractor.py` — Claude Haiku vision extraction. `EXTRACTION_PROMPT` is the core prompt; edit it when extraction quality degrades. Always pass `--platform` — auto-detection is unreliable.
- `scrapers/sheets_sync.py` — shared Google Sheets utility. `append_rows()` is the only public function; it auto-expands the sheet's row count if needed. Always non-fatal.

### Screenshot Conventions

Product reference screenshots live in `Product Screenshots/` organized by product line and Item ID (e.g. `owala-fs/owala-fs-001.png`). Processed marketplace screenshots move to `Data-Scrapers/processed/YYYY-MM-DD/` after extraction.

## Important Constraints

- **Never say "fake"** — output must use language like "no official match found" or "claim could not be verified." This is a deliberate legal/positioning decision.
- **Trust levels** — only Trust Level 4–5 sources go into `Verified_Products`. Never add data from reseller listings, Pinterest, Google Images, or user posts.
- **owala.com is geo-blocked** from some networks (resolves to Alibaba Cloud IP `47.96.81.233`). The scraper uses `owala.myshopify.com` which bypasses this. If you see SSL timeout errors on owala.com, this is the cause — do not switch back.
- **Chinese platform scraping** — Rednote, Taobao, and Xianyu have strong anti-bot measures. URL mode works best with a logged-in `--user-data-dir` session. Expect some URLs to fail; the script continues on failure.
