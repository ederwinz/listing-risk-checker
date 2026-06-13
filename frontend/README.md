# Listing Checker — Web App

Mobile-first web app for the listing risk checker. Users upload screenshots of products from Rednote, Taobao, or Xianyu and get a field-by-field risk report checked against ~10,000 official brand reference products.

---

## Setup

```bash
npm install
cp .env.local.example .env.local   # then fill in the values
npm run dev                         # http://localhost:3000
```

**`.env.local` keys** (all server-only — never sent to the browser):

```
ANTHROPIC_API_KEY=...        # from Data-Scrapers/.env
SUPABASE_URL=...             # from Data-Scrapers/.env
SUPABASE_SERVICE_KEY=...     # service role key from Supabase dashboard → Project Settings → API
```

---

## How it works

1. User taps **Check listings** → selects one or more screenshots from their phone gallery
2. Each image is sent in parallel to `POST /api/analyze`
3. The API route extracts product data from the image via Claude Haiku vision, then runs the comparison cascade against the Supabase `verified_products` table
4. Report cards fill in progressively as each result arrives — no waiting for the full batch

---

## Architecture

```
app/api/analyze/route.ts    POST endpoint: image → Report JSON
lib/extraction.ts           Claude Haiku vision extraction (same prompt as listing_extractor.py)
lib/comparison.ts           TypeScript port of comparison_engine.py — match cascade + risk scoring
lib/supabase.ts             Loads all verified_products, cached 1 hour
types/report.ts             Shared TypeScript types
components/ResultsList.tsx  Fires N parallel fetches, renders cards progressively
components/ReportCard.tsx   Thumbnail + RiskBadge + field-by-field RiskReport
```

The comparison logic in `lib/comparison.ts` is the TypeScript equivalent of `Data-Scrapers/scrapers/comparison_engine.py`. If you change matching thresholds or match types in one, mirror the change in the other.

---

## Commands

```bash
npm run dev       # dev server
npm run build     # production build
npx tsc --noEmit  # type check only
```

---

## Deployment

Deploy to Vercel. Set the three env vars above in **Project Settings → Environment Variables**. The `SUPABASE_SERVICE_KEY` is server-only and safe to use in Vercel — it is never exposed to the browser.

For production, consider switching to the Supabase anon key + enabling Row Level Security (public read on `verified_products`) to follow least-privilege.
