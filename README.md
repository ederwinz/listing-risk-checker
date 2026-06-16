# Listing Risk Checker — Data Pipeline

A data pipeline for an app that helps buyers in China verify whether overseas products sold on Rednote, Taobao, and Xianyu match official brand references. The output is a **mismatch risk score**, not a "fake/real" verdict.

The product is positioned as an **official-reference mismatch checker** — not an "AI fake detector."

---

## What it does

1. **`official_scraper.py`** — pulls product data (colorways, sizes, prices, images) from brand Shopify stores and builds a verified reference database.
2. **`listing_extractor.py`** — takes screenshots or URLs of Chinese marketplace listings and uses Claude vision to extract structured product data.
3. **`comparison_engine.py`** — matches extracted listings against the reference database and outputs a field-by-field risk report (brand / product line / colorway / size). Match cascade: EXACT → FUZZY_COLORWAY → color-tag → COLORWAY_NOT_FOUND → PRODUCT_LINE_NOT_FOUND → BRAND_NOT_FOUND.
4. **`brand_scout.py`** — screenshots Chinese marketplace search results, extracts overseas brand mentions, scores by platform weight, and probes for open Shopify APIs.

All tools write to local CSVs, sync to a shared Google Sheet, and sync to Supabase.

Aliases (Chinese ↔ English product/colorway name mappings) are stored in Supabase (`product_line_aliases`, `colorway_aliases` tables) and grow automatically as real listings are matched — both from local batch runs and from users of the web app.

---

## Current database

| Brand | Category |
|-------|----------|
| Owala | Drinkware |
| Rhode | Skincare & lip |
| e.l.f. Cosmetics | Cosmetics |
| Summer Fridays | Skincare |
| YoungLA | Apparel |
| Gymshark | Apparel |
| Alphalete | Activewear |
| NVGTN | Seamless leggings |
| Gymreapers | Lifting apparel & gear |
| Rhone | Men's apparel |
| Buff Bunny | Activewear |
| Popflex | Activewear |
| Alo Yoga | Activewear |
| Oner Active | Activewear |
| **Total** | **~10,000+ rows** |

---

## Setup

```bash
pip install -r Data-Scrapers/requirements.txt
playwright install chromium   # only needed for URL mode in listing_extractor
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
BRAND_CANDIDATES_TAB=Brand_Candidates
```

Place your Google service account key at `Data-Scrapers/google-credentials.json`. Both Google Sheets and Supabase syncs are non-fatal — scrapers still write to CSV if credentials are missing.

---

## Usage

All commands run from `Data-Scrapers/`. Use `/opt/anaconda3/bin/python3.12` — the system `/usr/bin/python3` is missing required packages.

### Scraping official reference data

```bash
# Scrape all brands
python scrapers/official_scraper.py

# Scrape one brand only
python scrapers/official_scraper.py --brand Rhode

# Check if a new brand is on open Shopify and list its collections
python scrapers/official_scraper.py --discover https://brand.com

# Scrape official product pages for brands without a public Shopify API
python scrapers/official_page_scraper.py \
  --brand Glossier --product-line "Balm Dotcom" \
  --id-prefix glossier-balmdotcom --urls glossier_urls.txt

# After every scraper run — bulk-sync new rows to Supabase
/opt/anaconda3/bin/python3.12 scripts/migrate_to_supabase.py
```

### Comparing marketplace listings

```bash
# Watch inbox/ and auto-compare any new screenshot (recommended — leave running in a terminal)
python scrapers/comparison_engine.py --watch

# Compare a single screenshot (extract + compare in one shot)
python scrapers/comparison_engine.py --screenshot inbox/photo.jpg

# Compare an already-extracted listing by ID
python scrapers/comparison_engine.py --testing-id XHS-001

# Batch-compare all unmatched test_listings rows
python scrapers/comparison_engine.py --all
```

With `--watch` running, take a screenshot (Cmd+Shift+4) and a field-by-field report prints within 2 seconds. The file moves to `processed/YYYY-MM-DD/` automatically.

### Extracting listings manually

```bash
# Extract from screenshots dropped in inbox/
python scrapers/listing_extractor.py --platform Rednote

# Extract from a URL file (one URL per line)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote

# URL mode with a logged-in Chrome session (for platforms requiring login)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote \
  --user-data-dir "/Users/you/Library/Application Support/Google/Chrome/Default"
```

### Brand discovery

```bash
# Scout all categories across all platforms
python scrapers/brand_scout.py --all --use-app

# Scout a single category
python scrapers/brand_scout.py --category fitness --platform Rednote

# Dry run (print what would run without doing anything)
python scrapers/brand_scout.py --all --dry-run
```

---

## Data schema

**`Verified_Products.csv`** — official reference database

| Column | Description |
|--------|-------------|
| Item ID | e.g. `owala-fs-001`, `rhode-liptint-001` |
| Brand | Owala, Rhode, … |
| Product Line | FreeSip, Peptide Lip Tint, … |
| Model Name | Full model name |
| Colorway Name | Shade or colorway (e.g. "Ribbon", "Out of the Blue") |
| Sizes Available | Bare numbers for Owala; descriptive for Rhode skincare |
| Status | Current, Special Edition, … |
| Price | Original/MSRP price |
| Sale Price | Discounted price, blank if none |
| Trust Level | 5 = official brand site, 4 = authorized retailer |
| Screenshot | Shopify CDN URL (target format) or legacy Yes/No string |

**`Test_Listings.csv`** — marketplace listings for comparison engine testing. IDs follow `XHS-NNN`. Rows with `NEEDS REVIEW:` in `notes` need manual inspection.

---

## Adding a new brand

### Path A — Brand is on open Shopify

```bash
python scrapers/official_scraper.py --discover https://brand.com
```

Copy the collection handles shown, add them to the `BRANDS` list in `official_scraper.py`:

```python
{
    "brand": "YourBrand",
    "collections": [
        {
            "url": "https://yourbrand.myshopify.com/collections/handle/products.json",
            "product_line": "Product Line Name",
            "model_name": "Model Name",
            "id_prefix": "yourbrand-line",
            # variant_strategy options:
            #   "by_color_option"  — product has Color + Size options (Owala, e.l.f., Gymreapers, Rhone)
            #   "by_product_title" — each product IS one shade; name from title (Rhode, Summer Fridays)
            #   "by_title_suffix"  — color after last " - " in title (Gymshark, Alphalete, Buff Bunny, Popflex, Alo Yoga)
            #   "by_title_prefix"  — color is title prefix; strip model_name from end (NVGTN)
            #   "by_title_pipe"    — color after last " | " in title (Oner Active)
            #   "by_title_parens"  — color in last parentheses (no current brand)
            "variant_strategy": "by_color_option",
        },
    ],
},
```

Then run `python scrapers/official_scraper.py --brand YourBrand`, followed by `migrate_to_supabase.py`.

### Path B — Brand is NOT on open Shopify

Create a text file with official product page URLs (one per line), then run:

```bash
python scrapers/official_page_scraper.py \
  --brand BrandName \
  --product-line "Product Line Name" \
  --id-prefix brandname-line \
  --urls urls.txt
```

---

## Important constraints

- **Never say "fake"** — output must use language like "no official match found" or "claim could not be verified." This is a deliberate legal/positioning decision.
- **Trust levels** — only Trust Level 4–5 sources go into `Verified_Products`. Never add data from reseller listings, Pinterest, Google Images, or user posts.
- **Owala geo-block** — `owala.com` resolves to an Alibaba Cloud IP from some networks. The scraper uses `owala.myshopify.com` which bypasses this — do not change it.
