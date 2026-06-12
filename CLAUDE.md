# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the data pipeline for a **listing risk checker** — an app that helps buyers in China verify whether overseas products sold on platforms like Rednote, Taobao, and Xianyu match official brand references. The output is a mismatch risk score, not a "fake/real" verdict (for legal reasons). The database currently covers Owala, Rhode, e.l.f. Cosmetics, YoungLA, Gymshark, Alphalete, NVGTN, Gymreapers, Rhone, Buff Bunny, Popflex, and Summer Fridays (~3,488 reference rows).

The product is positioned as an **official-reference mismatch checker**, not an "AI fake detector."

The database currently covers Owala, Rhode, e.l.f. Cosmetics, YoungLA, Gymshark, Alphalete, NVGTN, Gymreapers, Rhone, Buff Bunny, Popflex, Summer Fridays, Alo Yoga, and Oner Active (~4,928 reference rows).

## Running the Scrapers

All commands run from `Data-Scrapers/`. Use `/opt/anaconda3/bin/python3.12` (the system `/usr/bin/python3` is missing required packages):

```bash
# Scrape all brands
python scrapers/official_scraper.py

# Scrape one brand only
python scrapers/official_scraper.py --brand Rhode
python scrapers/official_scraper.py --brand Owala

# Check if a new brand is on open Shopify and list its collections
python scrapers/official_scraper.py --discover https://brand.com

# Scrape official product pages for brands without a public Shopify API
python scrapers/official_page_scraper.py \
  --brand Glossier \
  --product-line "Balm Dotcom" \
  --id-prefix glossier-balmdotcom \
  --urls glossier_urls.txt   # text file with one product page URL per line

# Scout Chinese marketplaces for trending overseas brands (outputs Brand_Candidates.csv)
python scrapers/brand_scout.py --all --use-app
python scrapers/brand_scout.py --category fitness --platform Rednote
# Flags:
#   --use-app            Use Rednote Mac app instead of Playwright browser
#   --force              Re-take screenshots even if they already exist for today
#   --screenshots-only   Take screenshots only, skip Claude extraction
#   --auto-scrape        Auto-scrape any newly discovered open-Shopify brands into Verified_Products
#   --dry-run            Print what would run without doing it
python scrapers/brand_scout.py --category fitness --platform Rednote --dry-run

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
cols = ['Item ID','Brand','Product Line','Model Name','Colorway Name','Sizes Available','Status','Price','Sale Price','Regions','Trust Level','Source Type','Source URL','Screenshot','Notes']
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
SUPABASE_URL=https://xxxx.supabase.co          # base URL only, no /rest/v1/
SUPABASE_SERVICE_KEY=eyJ...                     # service role key (bypasses RLS)
GOOGLE_CREDENTIALS_PATH=google-credentials.json
GOOGLE_SHEET_ID=15zxBq4slqjCM2ZQthFVzyKciJwl0ko10RnLb13z_7q4
VERIFIED_PRODUCTS_TAB=Verified_Products
TEST_LISTINGS_TAB=Test_Listings
BRAND_CANDIDATES_TAB=Brand_Candidates   # optional, used by brand_scout.py
```

`Data-Scrapers/google-credentials.json` must be a Google service account key with Editor access to the Google Sheet. Google Sheets sync is non-fatal — if credentials are missing, scrapers still write to CSV and Supabase. Supabase sync is also non-fatal — if keys are missing, scrapers fall back to CSV-only.

## Architecture

### Data Flow

```
Official sources (12 brands via Shopify JSON API — see BRANDS list in official_scraper.py)
    → official_scraper.py  [--brand <Name>]
    → Supabase: verified_products table  (primary; screenshot_url stores Shopify CDN URL directly)
    → Verified_Products.csv  (local backup, kept in sync)
    → Google Sheets "Verified_Products" tab  (human-readable view)

Chinese marketplace screenshots / URLs
    → listing_extractor.py (Claude Haiku vision)
    → Supabase: test_listings table  (primary)
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
- `Screenshot`: Shopify CDN URL for new rows (stable content-addressed URL, no download needed); legacy rows may have `"Yes"`/`"No"`. `"No"` and blank rows are auto-retried on the next scraper run
- Deduplication key is `(Brand, Product Line, Colorway Name)` — the scraper skips any triple already present (checked against Supabase first, CSV fallback)

**Owala Item ID prefixes:** `owala-fs`, `owala-kidsfs`, `owala-fstumbler`, `owala-fstwist`, `owala-sway`, `owala-kidstumbler`, `owala-smoothsip`

**Rhode Item ID prefixes:** `rhode-liptint`, `rhode-blush`, `rhode-bronze`, `rhode-liptreat`, `rhode-lipshape`, `rhode-glazingmilk`, `rhode-barrierbutter`, `rhode-spotwear`, `rhode-highlightmilk`

**e.l.f. Cosmetics Item ID prefixes:** `elf-foundation`, `elf-concealer`, `elf-primer`, `elf-blush`, `elf-bronzer`, `elf-highlighter`, `elf-eyeshadow`, `elf-eyeliner`, `elf-mascara`, `elf-lipstick`, `elf-lipgloss`, `elf-lipliner`, `elf-settingspray`, `elf-brushes`, `elf-skincare`

**YoungLA Item ID prefixes:** `yla-shirt`, `yla-shorts`, `yla-joggers`, `yla-hoodie`, `yla-tank`, `yla-compression`, `yla-womens`

**Gymshark Item ID prefixes:** `gs-adapt`, `gs-gains`, `gs-lift`, `gs-315`, `gs-apex`, `gs-elevate`, `gs-legacy`, `gs-crest`, `gs-hoodie`, `gs-joggers`, `gs-croptop`, `gs-shorts`, `gs-babytee`

**Alphalete Item ID prefixes:** `ala-amplify`, `ala-aura`, `ala-pump`, `ala-tenacity`, `ala-zero`, `ala-airtech`, `ala-terra`

**NVGTN Item ID prefixes:** `nvgtn-contour`, `nvgtn-camo`, `nvgtn-scrunch`, `nvgtn-lift`, `nvgtn-digital`, `nvgtn-solid`, `nvgtn-sig20`, `nvgtn-proshorts`

**Gymreapers Item ID prefixes:** `gr-shirt`, `gr-graphictee`, `gr-hoodie`, `gr-gear`, `gr-sleeve`, `gr-straps`

**Rhone Item ID prefixes:** `rh-commutershirt`, `rh-shorts`, `rh-hoodie`, `rh-commuterp`, `rh-golf`

**Buff Bunny Item ID prefixes:** `bb-airbrush`, `bb-nubre`, `bb-butter`, `bb-seamless`, `bb-poshknit`, `bb-miracle`

**Popflex Item ID prefixes:** `pfx-crisscross`, `pfx-cloudhoodie`, `pfx-pirouette`, `pfx-leggings`, `pfx-bras`, `pfx-shorts`

**Summer Fridays Item ID prefixes:** `sf-lbb`, `sf-dreamlipoil`, `sf-flushed`, `sf-lipliner`, `sf-bronzer`

**Alo Yoga Item ID prefixes:** `alo-airlift`, `alo-airbrush`, `alo-softsculpt`, `alo-alosoft`, `alo-conquer`

**Oner Active Item ID prefixes:** `oner-classicseamless`, `oner-softmotion`, `oner-effortless`, `oner-mellow`, `oner-accentuate`, `oner-airmove`

**Caveat on manually-entered rows:** The early manual entries for Kids' Freesip (`owala-kidsfs-*`) and FreeSip Tumbler (`owala-fstumbler-*`) have `Product Line = "Freesip"` instead of their correct product line names. This is intentional legacy data. As a side-effect, colorways shared between Freesip and Kids' Freesip (e.g. "Read My Lips") appear as duplicates in the CSV — this is expected and harmless for the reference database.

**`Test_Listings.csv`** — marketplace listings for testing the comparison engine. Testing IDs follow `XHS-NNN`. Rows with `NEEDS REVIEW:` in `notes` have missing required fields and need manual inspection.

### Key Files

- `scrapers/official_scraper.py` — multi-brand Shopify JSON API scraper. `BRANDS` list at the top configures each brand and its collections. Supports six variant strategies: `"by_color_option"` (Owala/e.l.f./Gymreapers/Rhone — product has Color+Size options), `"by_product_title"` (Rhode/Summer Fridays — each product IS one shade, name from title after stripping `model_name` prefix), `"by_title_suffix"` (Gymshark/Alphalete/Buff Bunny/Popflex/Alo Yoga — color after last ` - ` in title), `"by_title_prefix"` (NVGTN — color is the title prefix, strip `model_name` from end), `"by_title_pipe"` (Oner Active — color after last ` | ` in title), `"by_title_parens"` (color in last parentheses, e.g. `"Shirt (Black)"` — implemented but no current brand uses it). Stores Shopify CDN URL directly in `screenshot_url` — no image download or local file. Rows with `Screenshot="No"` or blank are retried on next run. Uses `owala.myshopify.com` for Owala (not `owala.com` — geo-blocked) and `rhodeskin.myshopify.com` for Rhode. Each Owala collection entry supports an optional `title_contains` filter. `--discover <url>` checks if any brand is on open Shopify and lists its collections. `detect_variant_strategy(products)` auto-detects the right strategy by peeking at product options and title patterns. `scrape_brand_dynamic(brand_name, shopify_handle)` fetches all collections and scrapes them dynamically — used by `brand_scout.py --auto-scrape`.
- `scrapers/official_page_scraper.py` — fallback for brands without a public Shopify API. Uses Playwright + Claude Haiku vision to screenshot official product pages and extract all colorways/shades. Output goes to `Verified_Products.csv` (Trust Level 5). Requires `playwright install chromium`.
- `scrapers/listing_extractor.py` — Claude Haiku vision extraction. `EXTRACTION_PROMPT` is the core prompt; edit it when extraction quality degrades. Always pass `--platform` — auto-detection is unreliable.
- `scrapers/brand_scout.py` — automated brand discovery. Screenshots Chinese marketplace search results (Rednote/Xianyu/Taobao), uses Claude Haiku vision to extract overseas brand names in parallel, scores by mention frequency × platform weight (Rednote 1.5×, Xianyu 1.2×, Taobao 1.0×), probes Shopify for open APIs, outputs `Brand_Candidates.csv` + Google Sheets "Brand_Candidates" tab. Score threshold is 3.0 (≈2 Rednote high-confidence mentions). Key flags: `--use-app` routes Rednote through the macOS Rednote app via AppleScript (avoids browser login walls); `--force` re-takes screenshots even if today's files already exist (default is to reuse cached screenshots and re-run extraction only); `--screenshots-only` skips extraction entirely; `--auto-scrape` automatically calls `scrape_brand_dynamic()` for any newly found open-Shopify brand. `SEARCH_QUERIES` (17 queries across fitness/beauty/streetwear/accessories) and `BRAND_ALIASES` at the top of the file are the main things to tune.
- `scrapers/sheets_sync.py` — shared Google Sheets utility. `append_rows()` is the only public function; it auto-expands the sheet's row count if needed. Always non-fatal.
- `scrapers/supabase_sync.py` — shared Supabase utility. Public functions: `load_existing()`, `next_id_num()`, `upsert_product()`, `upsert_listing()`, `upload_image()`, `update_screenshot_url()`. All non-fatal — returns safe defaults if `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` are not set. `upload_image()` is legacy — new rows use Shopify CDN URLs and do not upload to Supabase Storage.
- `scripts/migrate_to_supabase.py` — incremental backfill script. Upserts Verified_Products.csv and Test_Listings.csv to Supabase, skipping rows already present. Safe to re-run. No image migration step — image URLs are Shopify CDN and stored directly in the CSV/DB.

### Adding a New Brand

**Path A — Brand is on open Shopify** (like Owala, Rhode, e.l.f.):
```bash
python scrapers/official_scraper.py --discover https://brand.com
# → copy the collection handles shown, add to BRANDS in official_scraper.py
python scrapers/official_scraper.py --brand NewBrand
```

**Path B — Brand is NOT on open Shopify** (most big brands: Glossier, Stanley, etc.):
```bash
# 1. Create a text file with official product page URLs, one per line
# 2. Run:
python scrapers/official_page_scraper.py \
  --brand BrandName \
  --product-line "Product Line Name" \
  --id-prefix brandname-line \
  --urls urls.txt
```

**Path C — Manual entry** (for a handful of products):
- Edit `Verified_Products.csv` directly or via Google Sheets
- Run the force re-sync command (in "Running the Scrapers" above) to push changes to Sheets

### Screenshot Conventions

Official product images are stored as Shopify CDN URLs directly in the `Screenshot` / `screenshot_url` column — no download, no local file, no Supabase Storage upload. Shopify CDN URLs are stable (content-addressed). Any row where `Screenshot` is `"No"` or blank is automatically retried on the next scraper run. Processed marketplace screenshots (from `listing_extractor.py`) move to `Data-Scrapers/processed/YYYY-MM-DD/` after extraction.

## Important Constraints

- **Never say "fake"** — output must use language like "no official match found" or "claim could not be verified." This is a deliberate legal/positioning decision.
- **Trust levels** — only Trust Level 4–5 sources go into `Verified_Products`. Never add data from reseller listings, Pinterest, Google Images, or user posts.
- **owala.com is geo-blocked** from some networks (resolves to Alibaba Cloud IP `47.96.81.233`). The scraper uses `owala.myshopify.com` which bypasses this. If you see SSL timeout errors on owala.com, this is the cause — do not switch back.
- **Chinese platform scraping** — Rednote, Taobao, and Xianyu have strong anti-bot measures. URL mode works best with a logged-in `--user-data-dir` session. Expect some URLs to fail; the script continues on failure.
