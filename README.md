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

| Brand | Rows |
|-------|------|
| Owala | 122  |
| Rhode | 64   |

Owala covers: FreeSip, Kids' FreeSip, FreeSip Tumbler, FreeSip Sway, FreeSip Twist, Kids' Tumbler, SmoothSip

Rhode covers: Peptide Lip Tint, Peptide Lip Treatment, Peptide Lip Shape, Pocket Blush, Pocket Bronze, Glazing Milk, Barrier Butter, Spotwear, Highlight Milk

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

All commands run from `Data-Scrapers/`:

```bash
# Scrape official product data (all brands)
python scrapers/official_scraper.py

# Scrape one brand only
python scrapers/official_scraper.py --brand Rhode
python scrapers/official_scraper.py --brand Owala

# Extract listings from screenshots dropped in inbox/
python scrapers/listing_extractor.py --platform Rednote

# Extract listings from a URL file (one URL per line)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote

# URL mode with a logged-in Chrome session (for platforms requiring login)
python scrapers/listing_extractor.py --urls listing_urls.txt --platform Rednote \
  --user-data-dir "/Users/you/Library/Application Support/Google/Chrome/Default"
```

The official scraper automatically downloads product reference images to `Product Screenshots/` and retries any failed downloads on the next run.

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
| Screenshot | Yes/No — whether a reference image was downloaded |

**`Test_Listings.csv`** — marketplace listings for comparison engine testing. IDs follow `XHS-NNN`. Rows with `NEEDS REVIEW:` in `notes` need manual inspection.

---

## Adding a new brand

In `scrapers/official_scraper.py`, add an entry to the `BRANDS` list:

```python
{
    "brand": "YourBrand",
    "collections": [
        {
            "url": "https://yourbrand.myshopify.com/collections/handle/products.json",
            "product_line": "Product Line Name",
            "model_name": "Model Name",
            "id_prefix": "yourbrand-line",
            # Use "by_product_title" if each Shopify product is one shade (like Rhode)
            # Omit for the default Owala-style (color variants within a product)
            "variant_strategy": "by_product_title",
        },
    ],
},
```

---

## Important constraints

- **Never say "fake"** — output must use language like "no official match found" or "claim could not be verified." This is a deliberate legal/positioning decision.
- **Trust levels** — only Trust Level 4–5 sources go into `Verified_Products`. Never add data from reseller listings, Pinterest, Google Images, or user posts.
- **Owala geo-block** — `owala.com` resolves to an Alibaba Cloud IP (`47.96.81.233`) from some networks (VPN required). The scraper uses `owala.myshopify.com` which bypasses this.
