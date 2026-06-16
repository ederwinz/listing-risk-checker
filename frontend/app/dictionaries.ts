// dictionaries.ts — UI string table for English + Simplified Chinese.
// Drop into: frontend/app/dictionaries.ts
//
// Functions handle interpolation/pluralization. Brand, product, and colorway
// names are DATA (come from the API / listings) and are intentionally NOT
// translated — only the surrounding chrome is.

export const dictionaries = {
  en: {
    // ── meta ──
    metaTitle: "Counterpart — Listing Checker",
    metaDescription:
      "Check overseas listings against official brand records. Reports mismatch risk only.",

    // ── home ──
    eyebrow: "Reference mismatch checker",
    headline: ["Know what\u2019s", "official."],
    lede: "Screenshot a listing from Rednote, Taobao or Xianyu. We check every detail against the brand\u2019s own records.",
    peekSize: "Sunny Daze \u00b7 945 ml",
    statLine: "checked in 1.4s against 10,142 records",
    checkCta: "Check a listing",
    homeNote: "Reports mismatch risk only \u2014 never a verdict on authenticity.",
    aboutAria: "About",
    backAria: "Back",

    // ── results screen ──
    resultsTitle: "Results",
    resultsSub: (n: number) =>
      `${n} listing${n !== 1 ? "s" : ""} \u00b7 checked against official records`,
    tallyMatch: "Match",
    tallyPartial: "Partial",
    tallyNoMatch: "No match",
    checkMore: "Check more listings",

    // ── report card states ──
    cardQueued: "Queued\u2026",
    cardMatching: "Matching records\u2026",
    cardError: "Couldn\u2019t check this listing",
    cardFallbackSub: "Listing screenshot",

    // ── risk badge ──
    badge: {
      low: "Match confirmed",
      medium: "Partial match",
      high: "No match found",
      unverifiable: "Unverifiable",
    },

    // ── verdict banner ──
    verdictTitle: {
      low: "Matches official records",
      medium: "Partial match \u2014 review details",
      high: "No official match found",
      unverifiable: "Couldn\u2019t verify this listing",
    },
    verdictSubLow: "All checked details match the official record.",
    verdictSubUnverifiable: "Not enough detail to identify this product.",
    verdictSubIssues: (issues: number, checked: number) =>
      `${issues} of ${checked} details didn\u2019t match.`,

    // ── field rows ──
    fieldBrand: "Brand",
    fieldProductLine: "Product line",
    fieldColorway: "Colorway",
    fieldSize: "Size",
    notInListing: "not in listing",
    notProvided: "not provided",

    brandNotInDb: "Not in database",
    brandInDb: (n: number) => `In database \u00b7 ${n} products`,
    brandConfirmed: "Confirmed",
    knownBrands: (list: string) => `Known brands: ${list}`,

    plNotRecognized: "Not recognized",
    plRecognized: "Recognized",
    knownLines: (list: string) => `Known lines: ${list}`,

    cwNotProvidedNoLine: "not provided \u2014 product line not identified",
    cwExact: "Exact match",
    cwFuzzy: (name: string, pct: number) =>
      `No exact match \u2014 closest \u201c${name}\u201d at ${pct}%`,
    cwNotFound: "Not found in this product line",
    knownColorways: (list: string) => `Known colorways: ${list}`,

    sizeOfficiallyOffered: "Officially offered",
    sizeMismatch: "Size mismatch",

    // ── official reference ──
    detailCheck: "Detail check",
    officialReference: "Official reference",
    matchedRecord: "Matched record",
    closestRecord: "Closest record",
    noExactRecord: "No exact record matched",
    viewOnOfficial: "View on official site",
    reportNote:
      "This report flags mismatches against official records. It is not a determination of authenticity.",
  },

  zh: {
    // ── meta ──
    metaTitle: "Counterpart \u2014 \u5546\u54c1\u6bd4\u5bf9\u6838\u67e5",
    metaDescription: "\u5c06\u6d77\u5916\u5546\u54c1\u4e0e\u54c1\u724c\u5b98\u65b9\u8bb0\u5f55\u9010\u9879\u6bd4\u5bf9\uff0c\u4ec5\u63d0\u793a\u4fe1\u606f\u4e0d\u7b26\u98ce\u9669\u3002",

    // ── home ──
    eyebrow: "\u5b98\u65b9\u4fe1\u606f\u6bd4\u5bf9\u6838\u67e5",
    headline: ["\u4e00\u773c\u770b\u6e05", "\u5b98\u65b9\u4fe1\u606f\u3002"],
    lede: "\u622a\u56fe\u5c0f\u7ea2\u4e66\u3001\u6dd8\u5b9d\u6216\u95f2\u9c7c\u4e0a\u7684\u5546\u54c1\uff0c\u6211\u4eec\u4f1a\u9010\u9879\u6bd4\u5bf9\u54c1\u724c\u5b98\u65b9\u8bb0\u5f55\u3002",
    peekSize: "Sunny Daze \u00b7 945 \u6beb\u5347",
    statLine: "1.4 \u79d2\u5185\u6bd4\u5bf9 10,142 \u6761\u8bb0\u5f55",
    checkCta: "\u6838\u67e5\u5546\u54c1",
    homeNote: "\u4ec5\u63d0\u793a\u4fe1\u606f\u4e0d\u7b26\u98ce\u9669\uff0c\u7edd\u4e0d\u5bf9\u771f\u4f2a\u4e0b\u7ed3\u8bba\u3002",
    aboutAria: "\u5173\u4e8e",
    backAria: "\u8fd4\u56de",

    // ── results screen ──
    resultsTitle: "\u6838\u67e5\u7ed3\u679c",
    resultsSub: (n: number) => `\u5df2\u5bf9 ${n} \u4e2a\u5546\u54c1\u6bd4\u5bf9\u5b98\u65b9\u8bb0\u5f55`,
    tallyMatch: "\u5410\u5408",
    tallyPartial: "\u90e8\u5206\u5410\u5408",
    tallyNoMatch: "\u4e0d\u5410\u5408",
    checkMore: "\u6838\u67e5\u66f4\u591a\u5546\u54c1",

    // ── report card states ──
    cardQueued: "\u6392\u961f\u4e2d\u2026",
    cardMatching: "\u6bd4\u5bf9\u8bb0\u5f55\u4e2d\u2026",
    cardError: "\u65e0\u6cd5\u6838\u67e5\u6b64\u5546\u54c1",
    cardFallbackSub: "\u5546\u54c1\u622a\u56fe",

    // ── risk badge ──
    badge: {
      low: "\u4fe1\u606f\u5410\u5408",
      medium: "\u90e8\u5206\u5410\u5408",
      high: "\u672a\u627e\u5230\u5339\u914d",
      unverifiable: "\u65e0\u6cd5\u6838\u5b9e",
    },

    // ── verdict banner ──
    verdictTitle: {
      low: "\u4e0e\u5b98\u65b9\u8bb0\u5f55\u5410\u5408",
      medium: "\u90e8\u5206\u5410\u5408 \u2014 \u8bf7\u6838\u5bf9\u7ec6\u8282",
      high: "\u672a\u627e\u5230\u5b98\u65b9\u5339\u914d",
      unverifiable: "\u65e0\u6cd5\u6838\u5b9e\u6b64\u5546\u54c1",
    },
    verdictSubLow: "\u6240\u6709\u6838\u67e5\u7ec6\u8282\u5747\u4e0e\u5b98\u65b9\u8bb0\u5f55\u5410\u5408\u3002",
    verdictSubUnverifiable: "\u4fe1\u606f\u4e0d\u8db3\uff0c\u65e0\u6cd5\u8bc6\u522b\u6b64\u5546\u54c1\u3002",
    verdictSubIssues: (issues: number, checked: number) =>
      `${checked} \u9879\u4e2d\u6709 ${issues} \u9879\u4e0d\u7b26\u3002`,

    // ── field rows ──
    fieldBrand: "\u54c1\u724c",
    fieldProductLine: "\u4ea7\u54c1\u7cfb\u5217",
    fieldColorway: "\u989c\u8272",
    fieldSize: "\u89c4\u683c",
    notInListing: "\u5546\u54c1\u4e2d\u672a\u63d0\u4f9b",
    notProvided: "\u672a\u63d0\u4f9b",

    brandNotInDb: "\u672a\u6536\u5f55",
    brandInDb: (n: number) => `\u5df2\u6536\u5f55 \u00b7 ${n} \u6b3e\u4ea7\u54c1`,
    brandConfirmed: "\u5df2\u786e\u8ba4",
    knownBrands: (list: string) => `\u5df2\u77e5\u54c1\u724c\uff1a${list}`,

    plNotRecognized: "\u65e0\u6cd5\u8bc6\u522b",
    plRecognized: "\u5df2\u8bc6\u522b",
    knownLines: (list: string) => `\u5df2\u77e5\u7cfb\u5217\uff1a${list}`,

    cwNotProvidedNoLine: "\u672a\u63d0\u4f9b \u2014 \u4ea7\u54c1\u7cfb\u5217\u672a\u8bc6\u522b",
    cwExact: "\u5b8c\u5168\u5410\u5408",
    cwFuzzy: (name: string, pct: number) =>
      `\u65e0\u5b8c\u5168\u5339\u914d \u2014 \u6700\u63a5\u8fd1 \u201c${name}\u201d\uff0c\u76f8\u4f3c\u5ea6 ${pct}%`,
    cwNotFound: "\u8be5\u7cfb\u5217\u4e2d\u672a\u627e\u5230",
    knownColorways: (list: string) => `\u5df2\u77e5\u989c\u8272\uff1a${list}`,

    sizeOfficiallyOffered: "\u5b98\u65b9\u5728\u552e",
    sizeMismatch: "\u89c4\u683c\u4e0d\u7b26",

    // ── official reference ──
    detailCheck: "\u9010\u9879\u6838\u67e5",
    officialReference: "\u5b98\u65b9\u53c2\u8003",
    matchedRecord: "\u5df2\u5339\u914d\u8bb0\u5f55",
    closestRecord: "\u6700\u63a5\u8fd1\u7684\u8bb0\u5f55",
    noExactRecord: "\u672a\u627e\u5230\u5b8c\u5168\u5339\u914d\u7684\u8bb0\u5f55",
    viewOnOfficial: "\u67e5\u770b\u5b98\u65b9\u9875\u9762",
    reportNote: "\u672c\u62a5\u544a\u4ec5\u6807\u793a\u4e0e\u5b98\u65b9\u8bb0\u5f55\u4e0d\u7b26\u4e4b\u5904\uff0c\u5e76\u975e\u5bf9\u5546\u54c1\u771f\u4f2a\u7684\u5224\u5b9a\u3002",
  },
} as const;

export type Lang = keyof typeof dictionaries;
export type Dict = (typeof dictionaries)[Lang];

export const LANGS: Lang[] = ["en", "zh"];
export const DEFAULT_LANG: Lang = "en";

export function getDict(lang: string): Dict {
  return (dictionaries as Record<string, Dict>)[lang] ?? dictionaries[DEFAULT_LANG];
}
