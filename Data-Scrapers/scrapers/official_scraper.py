#!/usr/bin/env python3
"""
Scrapes official product data from brand Shopify stores and appends new entries
to Verified_Products.csv.  Supports multiple brands via the BRANDS config below.

Run this periodically to pick up new colorways/shades. Already-present items are
skipped (deduplication by Brand + Product Line + Colorway Name).  Any existing row
with Screenshot="No" will have its product image downloaded automatically.

Usage:
    cd Data-Scrapers
    python scrapers/official_scraper.py              # all brands
    python scrapers/official_scraper.py --brand Rhode   # Rhode only
    python scrapers/official_scraper.py --brand Owala   # Owala only
    python scrapers/official_scraper.py --discover https://brand.com  # check if brand is on open Shopify
"""

import argparse
import csv
import os
import re
import sys
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sheets_sync import append_rows as sheets_append
import supabase_sync

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
VERIFIED_CSV = BASE_DIR / "Verified_Products.csv"
SCREENSHOTS_DIR = BASE_DIR.parent / "Product Screenshots"

CSV_COLUMNS = [
    "Item ID", "Brand", "Product Line", "Model Name", "Colorway Name",
    "Sizes Available", "Status", "Price", "Sale Price", "Regions",
    "Trust Level", "Source Type", "Source URL", "Screenshot", "Notes",
]

# ── Brand & Collection Config ──────────────────────────────────────────────────
#
# variant_strategy options:
#   "by_color_option"  (default) — each Shopify product has multiple color variants;
#                                  one CSV row per color variant (used for Owala)
#   "by_product_title"           — each Shopify product IS one shade/colorway;
#                                  shade extracted from product title (used for Rhode)

BRANDS = [
    {
        "brand": "Owala",
        "collections": [
            {
                "url": "https://owala.myshopify.com/collections/freesip/products.json",
                "product_line": "Freesip",
                "model_name": "Freesip",
                "id_prefix": "owala-fs",
            },
            {
                "url": "https://owala.myshopify.com/collections/kids-freesip/products.json",
                "product_line": "Kids' Freesip",
                "model_name": "Kids' Freesip",
                "id_prefix": "owala-kidsfs",
            },
            {
                "url": "https://owala.myshopify.com/collections/freesip-tumbler/products.json",
                "product_line": "Freesip Tumbler",
                "model_name": "Freesip Tumbler",
                "id_prefix": "owala-fstumbler",
            },
            {
                "url": "https://owala.myshopify.com/collections/freesip-tumbler-sway/products.json",
                "product_line": "Freesip Sway",
                "model_name": "Freesip Sway",
                "id_prefix": "owala-sway",
                "title_contains": "Sway",
            },
            {
                "url": "https://owala.myshopify.com/collections/kids-products/products.json",
                "product_line": "Kids' Tumbler",
                "model_name": "Kids' Tumbler",
                "id_prefix": "owala-kidstumbler",
                "title_contains": "Tumbler",
            },
            {
                "url": "https://owala.myshopify.com/collections/smoothsip-coffee-mugs/products.json",
                "product_line": "SmoothSip",
                "model_name": "SmoothSip",
                "id_prefix": "owala-smoothsip",
            },
        ],
    },
    {
        "brand": "Rhode",
        "collections": [
            # Two lip-tint collections overlap; deduplication handles it
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-tint/products.json",
                "product_line": "Peptide Lip Tint",
                "model_name": "Peptide Lip Tint",
                "id_prefix": "rhode-liptint",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-tint-core/products.json",
                "product_line": "Peptide Lip Tint",
                "model_name": "Peptide Lip Tint",
                "id_prefix": "rhode-liptint",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/pocket-blush/products.json",
                "product_line": "Pocket Blush",
                "model_name": "Pocket Blush",
                "id_prefix": "rhode-blush",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/pocket-bronze/products.json",
                "product_line": "Pocket Bronze",
                "model_name": "Pocket Bronze",
                "id_prefix": "rhode-bronze",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-treatment/products.json",
                "product_line": "Peptide Lip Treatment",
                "model_name": "Peptide Lip Treatment",
                "id_prefix": "rhode-liptreat",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-shape/products.json",
                "product_line": "Peptide Lip Shape",
                "model_name": "Peptide Lip Shape",
                "id_prefix": "rhode-lipshape",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/glazing-milk/products.json",
                "product_line": "Glazing Milk",
                "model_name": "Glazing Milk",
                "id_prefix": "rhode-glazingmilk",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/barrier-butter/products.json",
                "product_line": "Barrier Butter",
                "model_name": "Barrier Butter",
                "id_prefix": "rhode-barrierbutter",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/spotwear/products.json",
                "product_line": "Spotwear",
                "model_name": "Spotwear",
                "id_prefix": "rhode-spotwear",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/highlight-milk/products.json",
                "product_line": "Highlight Milk",
                "model_name": "Highlight Milk",
                "id_prefix": "rhode-highlightmilk",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/glazing-mist/products.json",
                "product_line": "Glazing Mist",
                "model_name": "Glazing Mist",
                "id_prefix": "rhode-glazingmist",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-lip-boost/products.json",
                "product_line": "Peptide Lip Boost",
                "model_name": "Peptide Lip Boost",
                "id_prefix": "rhode-lipboost",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-eye-prep/products.json",
                "product_line": "Peptide Eye Prep",
                "model_name": "Peptide Eye Prep",
                "id_prefix": "rhode-eyeprep",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/peptide-glazing-fluid/products.json",
                "product_line": "Peptide Glazing Fluid",
                "model_name": "Peptide Glazing Fluid",
                "id_prefix": "rhode-glazingfluid",
                "variant_strategy": "by_product_title",
            },
            {
                "url": "https://rhodeskin.myshopify.com/collections/barrier-restore-cream/products.json",
                "product_line": "Barrier Restore Cream",
                "model_name": "Barrier Restore Cream",
                "id_prefix": "rhode-barriercream",
                "variant_strategy": "by_product_title",
            },
        ],
    },
    {
        "brand": "e.l.f. Cosmetics",
        "collections": [
            # ── Face ──────────────────────────────────────────────────────────
            {
                "url": "https://elfcosmetics.myshopify.com/collections/blush/products.json",
                "product_line": "Blush", "model_name": "Blush", "id_prefix": "elf-blush",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/bronzer/products.json",
                "product_line": "Bronzer", "model_name": "Bronzer", "id_prefix": "elf-bronzer",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/concealer/products.json",
                "product_line": "Concealer", "model_name": "Concealer", "id_prefix": "elf-concealer",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/foundation/products.json",
                "product_line": "Foundation", "model_name": "Foundation", "id_prefix": "elf-foundation",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/highlight-contour/products.json",
                "product_line": "Highlight & Contour", "model_name": "Highlight & Contour", "id_prefix": "elf-highlight",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/powder/products.json",
                "product_line": "Powder", "model_name": "Powder", "id_prefix": "elf-powder",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/primer/products.json",
                "product_line": "Primer", "model_name": "Primer", "id_prefix": "elf-primer",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/setting-spray/products.json",
                "product_line": "Setting Spray", "model_name": "Setting Spray", "id_prefix": "elf-settingspray",
            },
            # ── Eyes ──────────────────────────────────────────────────────────
            {
                "url": "https://elfcosmetics.myshopify.com/collections/eyebrows/products.json",
                "product_line": "Eyebrow", "model_name": "Eyebrow", "id_prefix": "elf-eyebrow",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/eyeliner/products.json",
                "product_line": "Eyeliner", "model_name": "Eyeliner", "id_prefix": "elf-eyeliner",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/eyeshadow/products.json",
                "product_line": "Eyeshadow", "model_name": "Eyeshadow", "id_prefix": "elf-eyeshadow",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/eyeshadow-palettes/products.json",
                "product_line": "Eyeshadow Palette", "model_name": "Eyeshadow Palette", "id_prefix": "elf-palette",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/mascara/products.json",
                "product_line": "Mascara", "model_name": "Mascara", "id_prefix": "elf-mascara",
            },
            # ── Lips ──────────────────────────────────────────────────────────
            {
                "url": "https://elfcosmetics.myshopify.com/collections/lip-colour/products.json",
                "product_line": "Lip Color", "model_name": "Lip Color", "id_prefix": "elf-lipcolor",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/lip-gloss/products.json",
                "product_line": "Lip Gloss", "model_name": "Lip Gloss", "id_prefix": "elf-lipgloss",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/lip-liner/products.json",
                "product_line": "Lip Liner", "model_name": "Lip Liner", "id_prefix": "elf-lipliner",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/lipstick/products.json",
                "product_line": "Lipstick", "model_name": "Lipstick", "id_prefix": "elf-lipstick",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/lip-care/products.json",
                "product_line": "Lip Care", "model_name": "Lip Care", "id_prefix": "elf-lipcare",
            },
            # ── Skincare ──────────────────────────────────────────────────────
            {
                "url": "https://elfcosmetics.myshopify.com/collections/cleanser/products.json",
                "product_line": "Cleanser", "model_name": "Cleanser", "id_prefix": "elf-cleanser",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/moisturizer/products.json",
                "product_line": "Moisturizer", "model_name": "Moisturizer", "id_prefix": "elf-moisturizer",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/boosters-serums/products.json",
                "product_line": "Serum", "model_name": "Serum", "id_prefix": "elf-serum",
            },
            {
                "url": "https://elfcosmetics.myshopify.com/collections/eye-cream-treatments/products.json",
                "product_line": "Eye Treatment", "model_name": "Eye Treatment", "id_prefix": "elf-eyetreatment",
            },
        ],
    },
    {
        "brand": "YoungLA",
        "collections": [
            {
                "url": "https://youngla.myshopify.com/collections/t-shirts/products.json",
                "product_line": "T-Shirt", "model_name": "T-Shirt", "id_prefix": "yla-tshirt",
            },
            {
                "url": "https://youngla.myshopify.com/collections/shorts/products.json",
                "product_line": "Shorts", "model_name": "Shorts", "id_prefix": "yla-shorts",
            },
            {
                "url": "https://youngla.myshopify.com/collections/joggers/products.json",
                "product_line": "Joggers", "model_name": "Joggers", "id_prefix": "yla-joggers",
            },
            {
                "url": "https://youngla.myshopify.com/collections/tanks/products.json",
                "product_line": "Tank", "model_name": "Tank", "id_prefix": "yla-tank",
            },
            {
                "url": "https://youngla.myshopify.com/collections/leggings/products.json",
                "product_line": "Leggings", "model_name": "Leggings", "id_prefix": "yla-leggings",
            },
            {
                "url": "https://youngla.myshopify.com/collections/bras/products.json",
                "product_line": "Sports Bra", "model_name": "Sports Bra", "id_prefix": "yla-bra",
            },
            {
                "url": "https://youngla.myshopify.com/collections/outerwear/products.json",
                "product_line": "Outerwear", "model_name": "Outerwear", "id_prefix": "yla-outerwear",
            },
            {
                "url": "https://youngla.myshopify.com/collections/jeans/products.json",
                "product_line": "Jeans", "model_name": "Jeans", "id_prefix": "yla-jeans",
            },
            {
                "url": "https://youngla.myshopify.com/collections/hats/products.json",
                "product_line": "Headwear", "model_name": "Headwear", "id_prefix": "yla-headwear",
            },
        ],
    },
    {
        "brand": "Gymshark",
        "collections": [
            # ── Iconic seamless lines ────────────────────────────────────────
            {
                "url": "https://gymshark.myshopify.com/collections/adapt-leggings/products.json",
                "product_line": "Adapt", "model_name": "Adapt", "id_prefix": "gs-adapt", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/gains-seamless/products.json",
                "product_line": "Gains Seamless", "model_name": "Gains Seamless", "id_prefix": "gs-gains", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/geo-seamless/products.json",
                "product_line": "Geo Seamless", "model_name": "Geo Seamless", "id_prefix": "gs-geo", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/lift-seamless/products.json",
                "product_line": "Lift Seamless", "model_name": "Lift Seamless", "id_prefix": "gs-lift", "variant_strategy": "by_title_suffix",
            },
            # ── Named product lines ──────────────────────────────────────────
            {
                "url": "https://gymshark.myshopify.com/collections/315/products.json",
                "product_line": "315", "model_name": "315", "id_prefix": "gs-315", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/apex/products.json",
                "product_line": "Apex", "model_name": "Apex", "id_prefix": "gs-apex", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/elevate/products.json",
                "product_line": "Elevate", "model_name": "Elevate", "id_prefix": "gs-elevate", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/legacy/products.json",
                "product_line": "Legacy", "model_name": "Legacy", "id_prefix": "gs-legacy", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/crest/products.json",
                "product_line": "Crest", "model_name": "Crest", "id_prefix": "gs-crest", "variant_strategy": "by_title_suffix",
            },
            # ── Core categories ──────────────────────────────────────────────
            {
                "url": "https://gymshark.myshopify.com/collections/hoodies/products.json",
                "product_line": "Hoodie", "model_name": "Hoodie", "id_prefix": "gs-hoodie", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/joggers/products.json",
                "product_line": "Joggers", "model_name": "Joggers", "id_prefix": "gs-joggers", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/crop-tops/products.json",
                "product_line": "Crop Top", "model_name": "Crop Top", "id_prefix": "gs-croptop", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/2-in-1-shorts/products.json",
                "product_line": "2-in-1 Shorts", "model_name": "2-in-1 Shorts", "id_prefix": "gs-shorts", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://gymshark.myshopify.com/collections/baby-tees/products.json",
                "product_line": "Baby Tee", "model_name": "Baby Tee", "id_prefix": "gs-babytee", "variant_strategy": "by_title_suffix",
            },
        ],
    },
    # ── Alphalete Athletics ──────────────────────────────────────────────────
    {
        "brand": "Alphalete",
        "collections": [
            {
                "url": "https://alphaleteathletics.myshopify.com/collections/womens-amplify/products.json",
                "product_line": "Amplify", "model_name": "Amplify", "id_prefix": "ala-amplify", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alphaleteathletics.myshopify.com/collections/womens-aura/products.json",
                "product_line": "Aura", "model_name": "Aura", "id_prefix": "ala-aura", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alphaleteathletics.myshopify.com/collections/womens-pump/products.json",
                "product_line": "Pump", "model_name": "Pump", "id_prefix": "ala-pump", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alphaleteathletics.myshopify.com/collections/womens-tenacity/products.json",
                "product_line": "Tenacity", "model_name": "Tenacity", "id_prefix": "ala-tenacity", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alphaleteathletics.myshopify.com/collections/mens-zero/products.json",
                "product_line": "Zero", "model_name": "Zero", "id_prefix": "ala-zero", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alphaleteathletics.myshopify.com/collections/mens-airtech/products.json",
                "product_line": "Airtech", "model_name": "Airtech", "id_prefix": "ala-airtech", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alphaleteathletics.myshopify.com/collections/trending-terra/products.json",
                "product_line": "Terra", "model_name": "Terra", "id_prefix": "ala-terra", "variant_strategy": "by_title_suffix",
            },
        ],
    },
    # ── NVGTN ────────────────────────────────────────────────────────────────
    {
        "brand": "NVGTN",
        "collections": [
            {
                "url": "https://nvgtn.myshopify.com/collections/contour-seamless-leggings/products.json",
                "product_line": "Contour Seamless", "model_name": "Contour Seamless Leggings", "id_prefix": "nvgtn-contour", "variant_strategy": "by_title_prefix",
            },
            {
                "url": "https://nvgtn.myshopify.com/collections/camo-seamless-leggings/products.json",
                "product_line": "Camo Seamless", "model_name": "Camo Seamless Leggings", "id_prefix": "nvgtn-camo", "variant_strategy": "by_title_prefix",
            },
            {
                "url": "https://nvgtn.myshopify.com/collections/scrunch-seamless-leggings/products.json",
                "product_line": "Scrunch Seamless", "model_name": "Scrunch Seamless Leggings", "id_prefix": "nvgtn-scrunch", "variant_strategy": "by_title_prefix",
            },
            {
                "url": "https://nvgtn.myshopify.com/collections/lift-seamless-leggings/products.json",
                "product_line": "Lift Seamless", "model_name": "Lift Seamless Leggings", "id_prefix": "nvgtn-lift", "variant_strategy": "by_title_prefix",
            },
            {
                "url": "https://nvgtn.myshopify.com/collections/digital-seamless-leggings/products.json",
                "product_line": "Digital Seamless", "model_name": "Digital Seamless Leggings", "id_prefix": "nvgtn-digital", "variant_strategy": "by_title_prefix",
            },
            {
                "url": "https://nvgtn.myshopify.com/collections/solid-seamless-leggings/products.json",
                "product_line": "Solid Seamless", "model_name": "Solid Seamless Leggings", "id_prefix": "nvgtn-solid", "variant_strategy": "by_title_prefix",
            },
            {
                "url": "https://nvgtn.myshopify.com/collections/signature-2-0-leggings/products.json",
                "product_line": "Signature 2.0", "model_name": "Signature 2.0 Leggings", "id_prefix": "nvgtn-sig20", "variant_strategy": "by_title_prefix",
            },
            {
                "url": "https://nvgtn.myshopify.com/collections/pro-shorts/products.json",
                "product_line": "Pro Shorts", "model_name": "Pro Shorts", "id_prefix": "nvgtn-proshorts", "variant_strategy": "by_title_prefix",
            },
        ],
    },
    # ── Gymreapers ───────────────────────────────────────────────────────────
    {
        "brand": "Gymreapers",
        "collections": [
            {
                "url": "https://gymreapers.myshopify.com/collections/shirts/products.json",
                "product_line": "Shirt", "model_name": "Shirt", "id_prefix": "gr-shirt", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://gymreapers.myshopify.com/collections/graphic-tees/products.json",
                "product_line": "Graphic Tee", "model_name": "Graphic Tee", "id_prefix": "gr-graphictee", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://gymreapers.myshopify.com/collections/hoodies-jackets/products.json",
                "product_line": "Hoodie", "model_name": "Hoodie", "id_prefix": "gr-hoodie", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://gymreapers.myshopify.com/collections/lifting-gear/products.json",
                "product_line": "Lifting Gear", "model_name": "Lifting Gear", "id_prefix": "gr-gear", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://gymreapers.myshopify.com/collections/knee-elbow-sleeves/products.json",
                "product_line": "Sleeves", "model_name": "Sleeves", "id_prefix": "gr-sleeve", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://gymreapers.myshopify.com/collections/lifting-straps/products.json",
                "product_line": "Lifting Straps", "model_name": "Lifting Straps", "id_prefix": "gr-straps", "variant_strategy": "by_color_option",
            },
        ],
    },
    # ── Rhone ────────────────────────────────────────────────────────────────
    {
        "brand": "Rhone",
        "collections": [
            {
                "url": "https://rhone.myshopify.com/collections/mens-commuter-shirt-collection/products.json",
                "product_line": "Commuter Shirt", "model_name": "Commuter Shirt", "id_prefix": "rh-commutershirt", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://rhone.myshopify.com/collections/mens-athletic-shorts/products.json",
                "product_line": "Athletic Shorts", "model_name": "Athletic Shorts", "id_prefix": "rh-shorts", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://rhone.myshopify.com/collections/mens-hoodies-pullovers/products.json",
                "product_line": "Hoodie", "model_name": "Hoodie", "id_prefix": "rh-hoodie", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://rhone.myshopify.com/collections/mens-commuter-pants/products.json",
                "product_line": "Commuter Pants", "model_name": "Commuter Pants", "id_prefix": "rh-commuterp", "variant_strategy": "by_color_option",
            },
            {
                "url": "https://rhone.myshopify.com/collections/mens-golf-apparel/products.json",
                "product_line": "Golf", "model_name": "Golf", "id_prefix": "rh-golf", "variant_strategy": "by_color_option",
            },
        ],
    },
    {
        "brand": "Buff Bunny",
        "store_domain": "buffbunny.com",
        "collections": [
            {
                "url": "https://buffbunny.myshopify.com/collections/airbrush-fabric/products.json",
                "product_line": "Airbrush", "model_name": "Airbrush", "id_prefix": "bb-airbrush", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://buffbunny.myshopify.com/collections/nubre-fabric/products.json",
                "product_line": "NuBre", "model_name": "NuBre", "id_prefix": "bb-nubre", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://buffbunny.myshopify.com/collections/butter-fabric/products.json",
                "product_line": "Butter", "model_name": "Butter", "id_prefix": "bb-butter", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://buffbunny.myshopify.com/collections/seamless-fabric/products.json",
                "product_line": "Seamless", "model_name": "Seamless", "id_prefix": "bb-seamless", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://buffbunny.myshopify.com/collections/poshknit-fabric/products.json",
                "product_line": "PoshKnit", "model_name": "PoshKnit", "id_prefix": "bb-poshknit", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://buffbunny.myshopify.com/collections/miracle-seamless/products.json",
                "product_line": "Miracle Seamless", "model_name": "Miracle Seamless", "id_prefix": "bb-miracle", "variant_strategy": "by_title_suffix",
            },
        ],
    },
    {
        "brand": "Popflex",
        "store_domain": "popflex.active",
        "collections": [
            {
                "url": "https://popflex.myshopify.com/collections/crisscross-hourglass-leggings/products.json",
                "product_line": "Crisscross Hourglass", "model_name": "Crisscross Hourglass", "id_prefix": "pfx-crisscross", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://popflex.myshopify.com/collections/cloud-hoodies/products.json",
                "product_line": "Cloud Hoodie", "model_name": "Cloud Hoodie", "id_prefix": "pfx-cloudhoodie", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://popflex.myshopify.com/collections/pirouette-skorts/products.json",
                "product_line": "Pirouette", "model_name": "Pirouette", "id_prefix": "pfx-pirouette", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://popflex.myshopify.com/collections/leggings/products.json",
                "product_line": "Leggings", "model_name": "Leggings", "id_prefix": "pfx-leggings", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://popflex.myshopify.com/collections/bras/products.json",
                "product_line": "Sports Bra", "model_name": "Sports Bra", "id_prefix": "pfx-bras", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://popflex.myshopify.com/collections/shorts/products.json",
                "product_line": "Shorts", "model_name": "Shorts", "id_prefix": "pfx-shorts", "variant_strategy": "by_title_suffix",
            },
        ],
    },
    {
        "brand": "Summer Fridays",
        "store_domain": "summerfridays.com",
        "collections": [
            {
                "url": "https://summerfridaysbeauty.myshopify.com/collections/all-lip-butter-balm/products.json",
                "product_line": "Lip Butter Balm", "model_name": "Lip Butter Balm", "id_prefix": "sf-lbb", "variant_strategy": "by_product_title",
            },
            {
                "url": "https://summerfridaysbeauty.myshopify.com/collections/dream-lip-oil-collection/products.json",
                "product_line": "Dream Lip Oil", "model_name": "Dream Lip Oil", "id_prefix": "sf-dreamlipoil", "variant_strategy": "by_product_title",
            },
            {
                "url": "https://summerfridaysbeauty.myshopify.com/collections/flushed-lip-stains/products.json",
                "product_line": "Flushed Lip Stain", "model_name": "Flushed Lip Stain", "id_prefix": "sf-flushed", "variant_strategy": "by_product_title",
            },
            {
                "url": "https://summerfridaysbeauty.myshopify.com/collections/softline-lip-liners/products.json",
                "product_line": "Softline Lip Liner", "model_name": "SoftLine Lip Liner", "id_prefix": "sf-lipliner", "variant_strategy": "by_product_title",
            },
            {
                "url": "https://summerfridaysbeauty.myshopify.com/collections/exchange-bronzer-butter-balm/products.json",
                "product_line": "Bronzer Butter Balm", "model_name": "Bronzer Butter Balm", "id_prefix": "sf-bronzer", "variant_strategy": "by_product_title",
            },
        ],
    },
    # ── Oner Active ─────────────────────────────────────────────────────────────
    {
        "brand": "Oner Active",
        "store_domain": "oner.com",
        "collections": [
            {
                "url": "https://oner-us.myshopify.com/collections/shop-classic-seamless/products.json",
                "product_line": "Classic Seamless", "model_name": "Classic Seamless", "id_prefix": "oner-classicseamless", "variant_strategy": "by_title_pipe",
            },
            {
                "url": "https://oner-us.myshopify.com/collections/softmotion/products.json",
                "product_line": "SoftMotion", "model_name": "SoftMotion", "id_prefix": "oner-softmotion", "variant_strategy": "by_title_pipe",
            },
            {
                "url": "https://oner-us.myshopify.com/collections/shop-effortless/products.json",
                "product_line": "Effortless", "model_name": "Effortless", "id_prefix": "oner-effortless", "variant_strategy": "by_title_pipe",
            },
            {
                "url": "https://oner-us.myshopify.com/collections/mellow/products.json",
                "product_line": "Mellow", "model_name": "Mellow", "id_prefix": "oner-mellow", "variant_strategy": "by_title_pipe",
            },
            {
                "url": "https://oner-us.myshopify.com/collections/accentuate/products.json",
                "product_line": "Accentuate", "model_name": "Accentuate", "id_prefix": "oner-accentuate", "variant_strategy": "by_title_pipe",
            },
            {
                "url": "https://oner-us.myshopify.com/collections/airmove/products.json",
                "product_line": "Airmove", "model_name": "Airmove", "id_prefix": "oner-airmove", "variant_strategy": "by_title_pipe",
            },
        ],
    },
    # ── Alo Yoga ────────────────────────────────────────────────────────────────
    {
        "brand": "Alo Yoga",
        "store_domain": "aloyoga.com",
        "collections": [
            {
                "url": "https://alo-yoga.myshopify.com/collections/airlift-leggings/products.json",
                "product_line": "Airlift Leggings", "model_name": "Airlift", "id_prefix": "alo-airlift", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alo-yoga.myshopify.com/collections/airbrush-leggings/products.json",
                "product_line": "Airbrush Leggings", "model_name": "Airbrush", "id_prefix": "alo-airbrush", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alo-yoga.myshopify.com/collections/alo-softsculpt-leggings/products.json",
                "product_line": "SoftSculpt Leggings", "model_name": "SoftSculpt", "id_prefix": "alo-softsculpt", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alo-yoga.myshopify.com/collections/alosoft-leggings/products.json",
                "product_line": "Alosoft Leggings", "model_name": "Alosoft", "id_prefix": "alo-alosoft", "variant_strategy": "by_title_suffix",
            },
            {
                "url": "https://alo-yoga.myshopify.com/collections/conquer/products.json",
                "product_line": "Conquer", "model_name": "Conquer", "id_prefix": "alo-conquer", "variant_strategy": "by_title_suffix",
            },
        ],
    },
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; brand-reference-scraper/2.0)"}


# ── Brand discovery ────────────────────────────────────────────────────────────

def discover_brand(url: str):
    """
    Check if a brand is on open Shopify and print its collections.
    Usage: python scrapers/official_scraper.py --discover https://brand.com
    """
    from urllib.parse import urlparse

    domain = urlparse(url).netloc or url
    domain = domain.removeprefix("www.")
    stem = domain.split(".")[0]

    candidates = [stem, f"{stem}-us", f"shop-{stem}", f"{stem}skin", f"{stem}beauty"]

    print(f"\nSearching Shopify for '{domain}'...")

    for handle in candidates:
        test_url = f"https://{handle}.myshopify.com/collections.json"
        try:
            resp = requests.get(test_url, headers=HEADERS, timeout=10, params={"limit": 250})
        except requests.ConnectionError:
            continue
        if resp.status_code != 200:
            continue

        try:
            data = resp.json()
        except Exception:
            continue  # 200 but non-JSON body = locked Shopify store

        collections = data.get("collections", [])
        if not collections and not data:
            continue

        print(f"\n✓ Found: {handle}.myshopify.com")
        print(f"\nCollections — choose which to add to BRANDS in official_scraper.py:\n")
        for col in collections:
            count = col.get("products_count", "?")
            print(f"  {col['handle']:<45} ({count} products)")
        print(f'\nExample BRANDS entry:')
        print(f'  {{"url": "https://{handle}.myshopify.com/collections/HANDLE/products.json",')
        print(f'   "product_line": "Product Line Name",')
        print(f'   "model_name": "Model Name",')
        print(f'   "id_prefix": "brand-line"}}')
        return

    print(f"\n✗ {domain} is not on open Shopify (tried: {', '.join(candidates)})")
    print("  → Use official_page_scraper.py with product page URLs instead.")


def detect_variant_strategy(products: list) -> str:
    """Guess the best extraction strategy by peeking at a few products."""
    if not products:
        return "by_product_title"
    for prod in products[:5]:
        for opt in prod.get("options", []):
            if opt.get("name", "").lower() in ("color", "colour"):
                return "by_color_option"
    titles = [p.get("title", "") for p in products[:10]]
    suffix_count = sum(1 for t in titles if " - " in t)
    paren_count = sum(1 for t in titles if t.rstrip().endswith(")") and "(" in t)
    if suffix_count > len(titles) / 2:
        return "by_title_suffix"
    if paren_count > len(titles) / 2:
        return "by_title_parens"
    return "by_product_title"


def scrape_brand_dynamic(brand_name: str, shopify_handle: str) -> int:
    """
    Discover all collections for a Shopify handle, auto-detect variant strategy,
    and scrape everything into Verified_Products. Returns number of new rows added.
    Called by brand_scout.py --auto-scrape for newly discovered open-Shopify brands.
    """
    base_url = f"https://{shopify_handle}.myshopify.com"

    resp = requests.get(f"{base_url}/collections.json", headers=HEADERS,
                        timeout=15, params={"limit": 250})
    if resp.status_code != 200:
        print(f"  [auto-scrape] Could not fetch collections for {shopify_handle}")
        return 0

    collections = resp.json().get("collections", [])
    if not collections:
        print(f"  [auto-scrape] No collections found for {shopify_handle}")
        return 0

    print(f"\n{'='*60}\n{brand_name} (auto-scraped from {shopify_handle})\n{'='*60}")

    existing = load_existing()
    updated_screenshots: dict[str, str] = {}
    all_rows: list[dict] = []
    brand_slug = re.sub(r"[^\w]", "", brand_name.lower())

    for col in collections:
        col_handle = col["handle"]
        col_title = col.get("title", col_handle)
        if col.get("products_count", 1) == 0:
            continue

        prod_url = f"{base_url}/collections/{col_handle}/products.json"
        prod_resp = requests.get(prod_url, headers=HEADERS, timeout=15, params={"limit": 5})
        if prod_resp.status_code != 200:
            continue
        sample = prod_resp.json().get("products", [])
        if not sample:
            continue

        strategy = detect_variant_strategy(sample)
        id_prefix = f"{brand_slug[:8]}-{re.sub(r'[^\\w]', '', col_handle)[:10]}"

        config = {
            "url": prod_url,
            "product_line": col_title,
            "model_name": col_title,
            "id_prefix": id_prefix,
            "variant_strategy": strategy,
        }
        rows = scrape_collection(config, brand_name, existing, updated_screenshots)
        all_rows.extend(rows)

    if all_rows:
        append_to_csv(all_rows)
        print(f"\n✓ Added {len(all_rows)} new row(s) for {brand_name}")
        tab = os.environ.get("VERIFIED_PRODUCTS_TAB", "Verified_Products")
        sheets_append(tab, all_rows, CSV_COLUMNS)

    if updated_screenshots:
        rewrite_csv_with_screenshot_updates(updated_screenshots)
        print(f"  Backfilled {len(updated_screenshots)} screenshot URL(s) — run migrate_to_supabase.py to sync.")

    return len(all_rows)


# ── Existing data ──────────────────────────────────────────────────────────────

def load_existing() -> dict[tuple, dict]:
    """
    Returns {(brand, product_line, colorway): {"item_id": ..., "screenshot": ...}}.
    Queries Supabase when configured; falls back to reading the local CSV.
    """
    sb = supabase_sync.load_existing()
    if sb:
        return sb
    if not VERIFIED_CSV.exists():
        return {}
    result = {}
    with open(VERIFIED_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            brand = r.get("Brand", "Owala")
            key = (brand, r["Product Line"], r["Colorway Name"])
            result[key] = {
                "item_id": r["Item ID"],
                "screenshot": r.get("Screenshot", "No"),
            }
    return result


def next_id_num(prefix: str) -> int:
    """Returns the next integer to use for a given ID prefix."""
    sb_num = supabase_sync.next_id_num(prefix)
    if sb_num is not None:
        return sb_num
    if not VERIFIED_CSV.exists():
        return 1
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    max_num = 0
    with open(VERIFIED_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = pattern.match(row.get("Item ID", ""))
            if m:
                max_num = max(max_num, int(m.group(1)))
    return max_num + 1


# ── Shopify API ────────────────────────────────────────────────────────────────

def fetch_products(url: str) -> list[dict]:
    all_products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(url, headers=HEADERS, timeout=30, params={"limit": 250, "page": page})
        resp.raise_for_status()
        products = resp.json().get("products", [])
        all_products.extend(products)
        if len(products) < 250:
            break
        page += 1
    return all_products


def option_key_for(options: list[dict], names: list[str]) -> str | None:
    for i, opt in enumerate(options):
        if opt["name"].lower() in names:
            return f"option{i + 1}"
    return None


def strip_units(size_str: str) -> str:
    """Remove trailing oz/ml units from purely numeric sizes. '32 oz' → '32'."""
    return re.sub(r"\s*(oz|ml|l)\b", "", size_str, flags=re.IGNORECASE).strip()


# ── Strategy: by_color_option (Owala) ─────────────────────────────────────────

def group_variants_by_colorway(products: list[dict], title_filter: str = "", store_domain: str = "owala.com") -> dict[str, dict]:
    """
    Returns {colorway_name: {sizes, price, sale_price, image_url, product_url}}.
    Each color variant within a product → one row.  Used for Owala-style products.
    """
    colorways: dict[str, dict] = {}

    for product in products:
        if title_filter and title_filter.lower() not in product.get("title", "").lower():
            continue

        options = product.get("options", [])
        color_key = option_key_for(options, ["color", "colour", "colorway"])
        size_key = option_key_for(options, ["size", "capacity", "volume"])

        images_by_variant: dict[int, str] = {}
        for img in product.get("images", []):
            for vid in img.get("variant_ids", []):
                images_by_variant[vid] = img["src"]
        default_image = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://{store_domain}/products/{product['handle']}"

        for variant in product.get("variants", []):
            colorway = (variant.get(color_key) or "").strip() if color_key else ""
            size_raw = (variant.get(size_key) or "").strip() if size_key else ""
            size = strip_units(size_raw)
            image_url = images_by_variant.get(variant["id"], default_image)

            current_price = variant.get("price") or "0"
            compare_price = variant.get("compare_at_price")
            if compare_price and float(compare_price) > float(current_price):
                price = f"${compare_price}"
                sale_price = f"${current_price}"
            else:
                price = f"${current_price}"
                sale_price = ""

            if not colorway:
                colorway = variant.get("title", "").split("/")[0].strip()
            if not colorway:
                continue

            if colorway not in colorways:
                colorways[colorway] = {
                    "sizes": [],
                    "price": price,
                    "sale_price": sale_price,
                    "image_url": image_url,
                    "product_url": product_url,
                }
            if size and size not in colorways[colorway]["sizes"]:
                colorways[colorway]["sizes"].append(size)

    def size_sort_key(s: str) -> float:
        m = re.match(r"[\d.]+", s)
        return float(m.group()) if m else 0

    for data in colorways.values():
        data["sizes"].sort(key=size_sort_key)

    return colorways


# ── Strategy: by_product_title (Rhode) ────────────────────────────────────────

def group_products_as_colorways(products: list[dict], model_name: str, store_domain: str = "rhodeskin.com") -> dict[str, dict]:
    """
    Returns {shade_name: {sizes, price, sale_price, image_url, product_url}}.
    Each Shopify product = one shade.  Shade extracted by stripping model_name prefix
    from the product title.  Products with no shade (skincare etc.) use "Original".
    Used for Rhode-style products.
    """
    colorways: dict[str, dict] = {}
    prefix = model_name.lower().strip()

    for product in products:
        title = product.get("title", "").lower().strip()
        shade = title.removeprefix(prefix).strip().title() or "Original"

        opts = product.get("options", [])
        size_key = option_key_for(opts, ["size", "capacity", "volume"])
        sizes: list[str] = []
        for v in product.get("variants", []):
            if size_key:
                sz = (v.get(size_key) or "").strip()
                if sz and sz != "Default Title" and sz not in sizes:
                    sizes.append(sz)

        variants = product.get("variants", [])
        price, sale_price = "$0", ""
        if variants:
            v = variants[0]
            current = v.get("price") or "0"
            compare = v.get("compare_at_price")
            if compare and float(compare) > float(current):
                price, sale_price = f"${compare}", f"${current}"
            else:
                price = f"${current}"

        image_url = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://{store_domain}/products/{product['handle']}"

        if shade not in colorways:
            colorways[shade] = {
                "sizes": sizes,
                "price": price,
                "sale_price": sale_price,
                "image_url": image_url,
                "product_url": product_url,
            }

    return colorways


# ── Strategy: by_title_prefix (NVGTN) ────────────────────────────────────────

def group_products_by_title_prefix(products: list[dict], model_name: str, store_domain: str) -> dict[str, dict]:
    """
    Color is the PREFIX of the title; model_name is the SUFFIX to strip.
    e.g. 'Black Speckled Contour Seamless Leggings' → model_name='Contour Seamless Leggings' → 'Black Speckled'.
    """
    colorways: dict[str, dict] = {}
    suffix = model_name.lower().strip()

    for product in products:
        title = product.get("title", "")
        title_lower = title.lower().strip()
        if title_lower.endswith(suffix):
            color = title[:len(title) - len(suffix)].strip().title() or "Original"
        else:
            color = title.strip().title() or "Original"

        opts = product.get("options", [])
        size_key = option_key_for(opts, ["size", "capacity", "volume"])
        sizes: list[str] = []
        for v in product.get("variants", []):
            if size_key:
                sz = (v.get(size_key) or "").strip()
                if sz and sz != "Default Title" and sz not in sizes:
                    sizes.append(sz)

        variants = product.get("variants", [])
        price, sale_price = "$0", ""
        if variants:
            v = variants[0]
            current = v.get("price") or "0"
            compare = v.get("compare_at_price")
            if compare and float(compare) > float(current):
                price, sale_price = f"${compare}", f"${current}"
            else:
                price = f"${current}"

        image_url = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://{store_domain}/products/{product['handle']}"

        if color not in colorways:
            colorways[color] = {"sizes": sizes, "price": price, "sale_price": sale_price,
                                 "image_url": image_url, "product_url": product_url}

    return colorways


# ── Strategy: by_title_parens (Born Primitive) ────────────────────────────────

def group_products_by_title_parens(products: list[dict], store_domain: str) -> dict[str, dict]:
    """
    Color is in parentheses at the end of the title.
    e.g. 'Versatile Short 5" (Black)' → 'Black'.
    """
    import re as _re
    colorways: dict[str, dict] = {}

    for product in products:
        title = product.get("title", "")
        m = _re.search(r'\(([^)]+)\)\s*$', title)
        color = m.group(1).strip() if m else title.strip().title() or "Original"

        opts = product.get("options", [])
        size_key = option_key_for(opts, ["size", "capacity", "volume"])
        sizes: list[str] = []
        for v in product.get("variants", []):
            if size_key:
                sz = (v.get(size_key) or "").strip()
                if sz and sz != "Default Title" and sz not in sizes:
                    sizes.append(sz)

        variants = product.get("variants", [])
        price, sale_price = "$0", ""
        if variants:
            v = variants[0]
            current = v.get("price") or "0"
            compare = v.get("compare_at_price")
            if compare and float(compare) > float(current):
                price, sale_price = f"${compare}", f"${current}"
            else:
                price = f"${current}"

        image_url = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://{store_domain}/products/{product['handle']}"

        if color not in colorways:
            colorways[color] = {"sizes": sizes, "price": price, "sale_price": sale_price,
                                 "image_url": image_url, "product_url": product_url}

    return colorways


# ── Strategy: by_title_suffix (Gymshark) ──────────────────────────────────────

def group_products_by_title_suffix(products: list[dict], store_domain: str) -> dict[str, dict]:
    """
    Returns {color: data} by extracting color from after the last ' - ' in the product title.
    Used for Gymshark-style products: 'Gymshark Adapt Camo Leggings - Black' → 'Black'.
    """
    colorways: dict[str, dict] = {}

    for product in products:
        title = product.get("title", "")
        color = title.split(" - ")[-1].strip() if " - " in title else "Original"

        opts = product.get("options", [])
        size_key = option_key_for(opts, ["size", "capacity", "volume"])
        sizes: list[str] = []
        for v in product.get("variants", []):
            if size_key:
                sz = (v.get(size_key) or "").strip()
                if sz and sz not in ("Default Title",) and sz not in sizes:
                    sizes.append(sz)

        variants = product.get("variants", [])
        price, sale_price = "$0", ""
        if variants:
            v = variants[0]
            current = v.get("price") or "0"
            compare = v.get("compare_at_price")
            if compare and float(compare) > float(current):
                price, sale_price = f"${compare}", f"${current}"
            else:
                price = f"${current}"

        image_url = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://{store_domain}/products/{product['handle']}"

        if color not in colorways:
            colorways[color] = {
                "sizes": sizes,
                "price": price,
                "sale_price": sale_price,
                "image_url": image_url,
                "product_url": product_url,
            }

    return colorways


# ── Strategy: by_title_pipe (Oner Active) ──────────────────────────────────────

def group_products_by_title_pipe(products: list[dict], store_domain: str) -> dict[str, dict]:
    """
    Returns {color: data} by extracting color from after the last ' | ' in the product title.
    Used for Oner-style products: 'SoftMotion™ Leggings | Black' → 'Black'.
    """
    colorways: dict[str, dict] = {}

    for product in products:
        title = product.get("title", "")
        color = title.split(" | ")[-1].strip() if " | " in title else "Original"

        opts = product.get("options", [])
        size_key = option_key_for(opts, ["size", "capacity", "volume"])
        sizes: list[str] = []
        for v in product.get("variants", []):
            if size_key:
                sz = (v.get(size_key) or "").strip()
                if sz and sz not in ("Default Title",) and sz not in sizes:
                    sizes.append(sz)

        variants = product.get("variants", [])
        price, sale_price = "$0", ""
        if variants:
            v = variants[0]
            current = v.get("price") or "0"
            compare = v.get("compare_at_price")
            if compare and float(compare) > float(current):
                price, sale_price = f"${compare}", f"${current}"
            else:
                price = f"${current}"

        image_url = product["images"][0]["src"] if product.get("images") else ""
        product_url = f"https://{store_domain}/products/{product['handle']}"

        if color not in colorways:
            colorways[color] = {"sizes": sizes, "price": price, "sale_price": sale_price,
                                 "image_url": image_url, "product_url": product_url}

    return colorways


# ── Image download ─────────────────────────────────────────────────────────────

def save_product_image(item_id: str, brand: str, id_prefix: str, image_url: str) -> str:
    """
    Returns the Shopify CDN URL directly — no download or local storage needed.
    Claude vision can access Shopify CDN URLs directly for image comparison.
    """
    return image_url or ""


# ── Scraping ───────────────────────────────────────────────────────────────────

def scrape_collection(
    config: dict,
    brand: str,
    existing: dict[tuple, dict],
    updated_screenshots: dict[str, str],
) -> list[dict]:
    """
    Scrape one collection config entry.  Returns list of new rows to append.
    Also mutates `updated_screenshots` with item_ids whose Screenshot field changed.
    """
    print(f"\n  [{config['product_line']}]  {config['url']}")
    try:
        products = fetch_products(config["url"])
    except requests.HTTPError as e:
        print(f"    HTTP {e.response.status_code} — collection URL may have changed, skipping.")
        return []
    except requests.ConnectionError as e:
        print(f"    Connection failed — check VPN / network and retry.")
        return []

    from urllib.parse import urlparse
    shopify_host = urlparse(config["url"]).netloc  # e.g. elfcosmetics.myshopify.com
    store_domain = shopify_host.replace(".myshopify.com", ".com")

    strategy = config.get("variant_strategy", "by_color_option")
    if strategy == "by_product_title":
        colorways = group_products_as_colorways(products, config["model_name"], store_domain)
    elif strategy == "by_title_suffix":
        colorways = group_products_by_title_suffix(products, store_domain)
    elif strategy == "by_title_prefix":
        colorways = group_products_by_title_prefix(products, config["model_name"], store_domain)
    elif strategy == "by_title_parens":
        colorways = group_products_by_title_parens(products, store_domain)
    elif strategy == "by_title_pipe":
        colorways = group_products_by_title_pipe(products, store_domain)
    else:
        title_filter = config.get("title_contains", "")
        colorways = group_variants_by_colorway(products, title_filter, store_domain)

    seq = next_id_num(config["id_prefix"])
    new_rows: list[dict] = []

    for colorway, data in colorways.items():
        key = (brand, config["product_line"], colorway)

        if key in existing:
            info = existing[key]
            has_screenshot = (info["screenshot"] or "").startswith("https://cdn.shopify.com/")
            if not has_screenshot and data.get("image_url"):
                img_result = save_product_image(
                    info["item_id"], brand, config["id_prefix"], data["image_url"]
                )
                if img_result:
                    updated_screenshots[info["item_id"]] = img_result
                    print(f"    img  {info['item_id']}  {colorway}")
            else:
                print(f"    skip {colorway}")
            continue

        item_id = f"{config['id_prefix']}-{seq:03d}"
        sizes_str = ", ".join(data["sizes"])
        sale_label = f" → sale {data['sale_price']}" if data["sale_price"] else ""

        img_result = save_product_image(item_id, brand, config["id_prefix"], data["image_url"])

        row = {
            "Item ID": item_id,
            "Brand": brand,
            "Product Line": config["product_line"],
            "Model Name": config["model_name"],
            "Colorway Name": colorway,
            "Sizes Available": sizes_str,
            "Status": "Current",
            "Price": data["price"],
            "Sale Price": data["sale_price"],
            "Regions": "",
            "Trust Level": "5",
            "Source Type": "Official Page",
            "Source URL": data["product_url"],
            "Screenshot": img_result,
            "Notes": f"Auto-scraped {datetime.now().strftime('%Y-%m-%d')}",
        }
        new_rows.append(row)
        existing[key] = {"item_id": item_id, "screenshot": img_result}
        seq += 1
        print(f"    +  {item_id}  {colorway}  ({sizes_str})  {data['price']}{sale_label}"
              + ("  [img]" if img_result else ""))

    return new_rows


# ── CSV I/O ────────────────────────────────────────────────────────────────────

def append_to_csv(rows: list[dict]):
    file_exists = VERIFIED_CSV.exists()
    with open(VERIFIED_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def rewrite_csv_with_screenshot_updates(updates: dict[str, str]):
    """Flush in-place Screenshot="Yes" updates back to the CSV."""
    rows = list(csv.DictReader(open(VERIFIED_CSV, newline="", encoding="utf-8")))
    for row in rows:
        if row["Item ID"] in updates:
            row["Screenshot"] = updates[row["Item ID"]]
    with open(VERIFIED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


# ── Full Sheets sync (used after backfill to update existing rows) ─────────────

def _full_sheets_sync(tab: str):
    try:
        from sheets_sync import _get_client
        rows = list(csv.DictReader(open(VERIFIED_CSV, newline="", encoding="utf-8")))
        client = _get_client()
        ws = client.open_by_key(os.environ["GOOGLE_SHEET_ID"]).worksheet(tab)
        ws.clear()
        data = [CSV_COLUMNS] + [[str(r.get(c, "")) for c in CSV_COLUMNS] for r in rows]
        if ws.row_count < len(data) + 10:
            ws.add_rows(len(data) + 10 - ws.row_count)
        ws.update(values=data, range_name="A1", value_input_option="RAW")
        print(f"  [Sheets] Full sync complete — {len(rows)} rows")
    except Exception as e:
        print(f"  [Sheets] Full sync failed ({e}) — CSV is up to date")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape official product data into Verified_Products.csv")
    parser.add_argument("--brand", help="Only scrape this brand (e.g. Owala, Rhode)")
    parser.add_argument("--discover", metavar="URL",
                        help="Check if a brand is on open Shopify and list its collections")
    args = parser.parse_args()

    if args.discover:
        discover_brand(args.discover)
        return

    existing = load_existing()
    updated_screenshots: dict[str, str] = {}
    all_new: list[dict] = []

    brands_to_run = [
        b for b in BRANDS
        if not args.brand or b["brand"].lower() == args.brand.lower()
    ]
    if not brands_to_run:
        print(f"Unknown brand '{args.brand}'. Available: {[b['brand'] for b in BRANDS]}")
        return

    for brand_config in brands_to_run:
        brand = brand_config["brand"]
        print(f"\n{'='*60}\n{brand}\n{'='*60}")
        for col_config in brand_config["collections"]:
            rows = scrape_collection(col_config, brand, existing, updated_screenshots)
            all_new.extend(rows)

    if all_new:
        append_to_csv(all_new)
        print(f"\n✓ Added {len(all_new)} new row(s) to {VERIFIED_CSV.name}")
        tab = os.environ.get("VERIFIED_PRODUCTS_TAB", "Verified_Products")
        sheets_append(tab, all_new, CSV_COLUMNS)

    if updated_screenshots:
        rewrite_csv_with_screenshot_updates(updated_screenshots)
        print(f"✓ Backfilled images for {len(updated_screenshots)} existing row(s)")
        for item_id, screenshot_val in updated_screenshots.items():
            supabase_sync.update_screenshot_url(item_id, screenshot_val)
        tab = os.environ.get("VERIFIED_PRODUCTS_TAB", "Verified_Products")
        _full_sheets_sync(tab)

    if not all_new and not updated_screenshots:
        print("\nNo new products and no missing images — database is up to date.")


if __name__ == "__main__":
    main()
