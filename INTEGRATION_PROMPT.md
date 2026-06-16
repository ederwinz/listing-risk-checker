# Add a Simplified-Chinese version of the UI

I want a **separate Chinese (`zh`) version** of the Counterpart frontend, served at its
own URL, with the English version untouched at the existing route. Use locale-segment
routing — one codebase, two locales — not a duplicated page.

Tech: Next.js 16 App Router, React 19, Tailwind v4. Strings are currently hardcoded
inline in `app/page.tsx` and `components/*.tsx`.

## 1. Drop in the dictionary
Add `app/dictionaries.ts` (provided alongside this prompt). It has full `en` + `zh`
string tables; interpolated strings are functions (`brandInDb(n)`, `verdictSubIssues(i, c)`,
`cwFuzzy(name, pct)`, etc.). `getDict(lang)`, `LANGS`, `DEFAULT_LANG` are exported.

## 2. Locale routing
- Move `app/page.tsx` → `app/[lang]/page.tsx`.
- Move `app/layout.tsx` → `app/[lang]/layout.tsx`.
- Add a root `app/page.tsx` (or `middleware.ts`) that redirects `/` → `/en`.
- In `generateStaticParams`, return `LANGS.map(lang => ({ lang }))`.
- The page reads `params.lang`, calls `const t = getDict(lang)`, and threads `t` (and
  `lang`) down to the components that render text.

Result: `/en` = English, `/zh` = Chinese.

## 3. Thread the dictionary into components
These components render hardcoded English — change each to accept the strings it needs
(pass the whole `t` object, or just the slice each one uses):

- **`page.tsx`** — `eyebrow`, `headline` (array of 2 lines), `lede`, `peekSize`,
  `statLine`, `checkCta` area, `homeNote`, `resultsTitle`, `resultsSub(n)`, the two
  `aria-label`s (`backAria`, `aboutAria`).
- **`UploadButton.tsx`** — `checkCta`.
- **`ResultsList.tsx`** — `tallyMatch` / `tallyPartial` / `tallyNoMatch`, `checkMore`.
- **`ReportCard.tsx`** — `cardQueued`, `cardMatching`, `cardError`, `cardFallbackSub`.
- **`RiskBadge.tsx`** — replace the `LABELS` map with `t.badge[level]`.
- **`FieldRow.tsx`** — the `not in listing` fallback → `t.notInListing` (pass it in).
- **`RiskReport.tsx`** — the big one. Replace every literal: `VERDICT_TITLE` → `t.verdictTitle`,
  the `verdictSub` branches → `t.verdictSubLow` / `t.verdictSubUnverifiable` /
  `t.verdictSubIssues(issues, checked)`, the brand/product-line/colorway/size result
  strings → their `t.*` equivalents, field labels (`Brand`→`t.fieldBrand`, etc.),
  `Detail check`, `Official reference`, `Matched record`/`Closest record`,
  `No exact record matched`, `View on official site`, and the closing `reportNote`.

## 4. Fonts (required for Chinese)
`layout.tsx` only loads Latin fonts (Source Serif 4 / Hanken Grotesk / Geist Mono),
which have no CJK glyphs. In `app/[lang]/layout.tsx`:

```ts
import { Noto_Sans_SC, Noto_Serif_SC } from "next/font/google";

const cjkBody = Noto_Sans_SC({ subsets: ["latin"], weight: ["400","500","600","700"], variable: "--font-body-cjk", display: "swap" });
const cjkHead = Noto_Serif_SC({ subsets: ["latin"], weight: ["400","500","600","700"], variable: "--font-head-cjk", display: "swap" });
```

Set `<html lang={lang}>`. When `lang === "zh"`, append the CJK font variables and make
the CSS `--font-head` / `--font-body` fall back to them, e.g. stack
`var(--font-head), var(--font-head-cjk)`. Keep the Latin fonts first so brand names
(Owala, FreeSip) still render in the Latin face. Set `metadata` from `t.metaTitle` /
`t.metaDescription` via `generateMetadata`.

## 5. Language switch (optional)
A small toggle in the top bar linking `/en` ⇄ `/zh` (preserve nothing else — these are
stateless). Place it next to `BrandMark` or the shield icon.

## What to keep in English (do NOT translate)
- Brand / product / colorway names: Owala, FreeSip, Rhode, Sunny Daze, etc. — these come
  from the API/listings and are real identifiers. The `+11` chip and brand chips stay.
- Units like `ml` may stay or become `毫升` (the dictionary uses `毫升` in `peekSize`).
- Platform names in the lede are already localized in the dict (小红书 / 淘宝 / 闲鱼).

## Known gap — server-generated strings
`RiskReport.tsx` derives the size-mismatch text by parsing `discrepancy.message`, which
is **English text returned by `/api/analyze`**. The dictionary can't reach it. To fully
localize size mismatches, either:
- return a structured discrepancy (e.g. `{ field, offered: [...], claimed }`) from the API
  and format it client-side with the dict, or
- have `/api/analyze` accept a `lang` param and return localized messages.
Flag this and pick one; everything else localizes purely client-side.

## Acceptance
- `/en` renders identically to today.
- `/zh` renders all chrome in Simplified Chinese with Noto SC fonts, brand names still Latin.
- No hardcoded user-facing English left in the components (except intentional brand data).
- `npm run build` passes.
