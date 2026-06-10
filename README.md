# Listing Risk Checker — Data Pipeline

A data pipeline for an app that helps buyers in China verify whether overseas products sold on Rednote, Taobao, and Xianyu match official brand references. The output is a **mismatch risk score**, not a "fake/real" verdict.

The product is positioned as an **official-reference mismatch checker** — not an "AI fake detector."

---

## What it does

1. **`official_scraper.py`** — pulls product data (colorways, sizes, prices, images) from brand Shopify stores and builds a verified reference database.
2. **`listing_extractor.py`** — takes screenshots or URLs of Chinese marketplace listings and uses Claude vision to extract structured product data for comparison testing.

Both tools write to local CSVs and sync to a shared Google Sheet.

---

## Current database

| Brand | Notes |
|-------|-------|
| YoungLA | Apparel |
| Gymshark | Apparel |
| e.l.f. Cosmetics | Cosmetics |
| Rhone | Men's apparel |
| NVGTN | Seamless leggings |
| Gymreapers | Lifting apparel & gear |
| Alphalete | Activewear |
| Owala | Drinkware |
| Rhode | Skincare & lip |
| Buff Bunny | Activewear |
| Popflex | Activewear |
| Summer Fridays | Skincare |
| **Total** | **~3,488 rows** |

---

## Setup

```bash
pip install -r Data-Scrapers/requirements.txt
playwright install chromium   # only needed for URL mode in listing_extractor
```

Copy `Data-Scrapers/.env.example` to `Data-Scrapers/.env` and fill in:

```
ANTHROPIC_API_KEY=...
GOOGLE_CREDENTIALS_PATH=google-credentials.json
GOOGLE_SHEET_ID=15zxBq4slqjCM2ZQthFVzyKciJwl0ko10RnLb13z_7q4
VERIFIED_PRODUCTS_TAB=Verified_Products
TEST_LISTINGS_TAB=Test_Listings
```

Place your Google service account key at `Data-Scrapers/google-credentials.json`. Google Sheets sync is non-fatal — scrapers still work without it.

---

## Usage

All commands run from `Data-Scrapers/`. Use `/opt/anaconda3/bin/python3.12` — the system `/usr/bin/python3` is missing required packages:

```bash
# Scrape official product data (all brands)
python scrapers/official_scraper.py

# Scrape one brand only
python scrapers/official_scraper.py --brand Rhode
python scrapers/official_scraper.py --brand Owala

# Check if a new brand is on open Shopify and list its collections
python scrapers/official_scraper.py --discover https://brand.com

# Scrape official product pages for brands without a public Shopify API
python scrapers/official_page_scraper.py \
  --brand Glossier --product-line "Balm Dotcom" \
  --id-prefix glossier-balmdotcom --urls glossier_urls.txt

# Extract listings from screenshots dropped in inbox/
python scrapers/listing_extractor.py --platform Rednote

# Extract listings from a URL file (one URL per line)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote

# URL mode with a logged-in Chrome session (for platforms requiring login)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote \
  --user-data-dir "/Users/you/Library/Application Support/Google/Chrome/Default"
```

The official scraper stores Shopify CDN URLs directly as reference images — no local download. Any row with a missing image URL is retried on the next run.

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
| Screenshot | Shopify CDN URL (new rows) or Yes/No (legacy rows) |

**`Test_Listings.csv`** — marketplace listings for comparison engine testing. IDs follow `XHS-NNN`. Rows with `NEEDS REVIEW:` in `notes` need manual inspection.

---

## Adding a new brand

### Step 1: Check if the brand is on open Shopify

```bash
python scrapers/official_scraper.py --discover https://brand.com
```

If it finds a match, it prints all available collections. Copy the ones you want into the `BRANDS` list in `official_scraper.py`:

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
            #   "by_color_option"  (default) — product has Color + Size options (Owala, e.l.f., Gymreapers, Rhone)
            #   "by_product_title"           — each product IS one shade; name from title (Rhode)
            #   "by_title_suffix"            — color after last " - " in title (Gymshark, Alphalete)
            #   "by_title_prefix"            — color is title prefix; strip model_name from end (NVGTN)
            #   "by_title_parens"            — color in last parentheses: "Shirt (Black)" (no current brand)
            "variant_strategy": "by_color_option",
        },
    ],
},
```

Then run: `python scrapers/official_scraper.py --brand YourBrand`

### Step 2 (fallback): If the brand is NOT on open Shopify

Create a text file with official product page URLs (one per line), then run:

```bash
python scrapers/official_page_scraper.py \
  --brand BrandName \
  --product-line "Product Line Name" \
  --id-prefix brandname-line \
  --urls urls.txt
```

The scraper screenshots each page and uses Claude vision to extract all visible colorways. Each colorway becomes a row in `Verified_Products.csv`.

---

## Important constraints

- **Never say "fake"** — output must use language like "no official match found" or "claim could not be verified." This is a deliberate legal/positioning decision.
- **Trust levels** — only Trust Level 4–5 sources go into `Verified_Products`. Never add data from reseller listings, Pinterest, Google Images, or user posts.
- **Owala geo-block** — `owala.com` resolves to an Alibaba Cloud IP (`47.96.81.233`) from some networks (VPN required). The scraper uses `owala.myshopify.com` which bypasses this.
