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
3. The API route runs three things in parallel: Claude Haiku vision extraction, loading `verified_products` from Supabase (1-hour cache), and loading aliases from Supabase (1-hour cache)
4. The comparison cascade runs: EXACT → FUZZY_COLORWAY (name similarity ≥ 0.75) → color-tag match (visual color → colorway via aliases) → COLORWAY_NOT_FOUND
5. An **overall match score** (0–100) is computed as an equal-weight average of brand + product line + colorway + size checks — only fields that were actually checkable are included
6. Report cards fill in progressively as each result arrives — no waiting for the full batch
7. Confirmed matches with Chinese model names auto-log new aliases to Supabase (fire-and-forget, non-blocking)

---

## Architecture

```
app/api/analyze/route.ts    POST endpoint: image → Report JSON
lib/extraction.ts           Claude Haiku vision extraction (same prompt as listing_extractor.py)
lib/comparison.ts           TypeScript port of comparison_engine.py — match cascade + overall_score
lib/supabase.ts             verified_products + aliases loaded from Supabase, cached 1 hour each
lib/alias-logger.ts         Fire-and-forget: logs new Chinese aliases on confirmed matches
types/report.ts             Shared TypeScript types (Report, Extracted, VerifiedProduct, etc.)
components/ResultsList.tsx  Fires N parallel fetches, renders cards progressively
components/ReportCard.tsx   Thumbnail + RiskBadge + field-by-field RiskReport
```

The comparison logic in `lib/comparison.ts` is the TypeScript equivalent of `Data-Scrapers/scrapers/comparison_engine.py`. If you change matching thresholds or match types in one, mirror the change in the other.

`Report.overall_score` is an equal-weight average of brand (0 or 1), product line (0 or 1), colorway (0–1 from the tier confidence), and size (0 or 1) — null fields are excluded. `expected_matchconfidence` still holds the raw colorway-tier confidence and is used by the alias logger as a quality gate.

---

## Commands

```bash
npm run dev                          # dev server
npm run build                        # production build
./node_modules/.bin/tsc --noEmit    # type check — do NOT use npx tsc (installs wrong package)
```

---

## Deployment

Deploy to Vercel. Set the three env vars above in **Project Settings → Environment Variables**. The `SUPABASE_SERVICE_KEY` is server-only and safe to use in Vercel — it is never exposed to the browser.

For production, consider switching to the Supabase anon key + enabling Row Level Security (public read on `verified_products`) to follow least-privilege.
