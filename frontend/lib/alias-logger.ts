import { upsertProductLineAlias, upsertColorwayAlias } from "@/lib/supabase";
import type { Extracted, Report } from "@/types/report";

const CJK = /[一-鿿]+/g;

function norm(s: string): string {
  return s.toLowerCase().replace(/[^\w\s]/g, "").trim();
}

export async function tryLogAlias(extracted: Extracted, report: Report): Promise<void> {
  if (!report.expected_matchid) return;
  if (report.match_context?.color_tag_match) return;
  if (report.expected_matchconfidence < 0.75) return;

  const modelname = extracted.claimed_modelname ?? "";
  if (!modelname) return;

  CJK.lastIndex = 0;
  if (!CJK.test(modelname)) return;

  const brand = extracted.claimed_brand;
  const productLine = report.matched_product_line;
  const colorwayName = report.matched_colorway_name;

  if (!productLine) return;

  const writes: Promise<void>[] = [];

  // Product-line aliases — first word of the official name must appear in modelname
  const plAnchor = norm(productLine).split(" ")[0];
  if (plAnchor && norm(modelname).includes(plAnchor)) {
    CJK.lastIndex = 0;
    const seqs = (modelname.match(CJK) ?? []).filter((s) => s.length >= 2);
    for (const seq of seqs) {
      writes.push(upsertProductLineAlias(brand, productLine, seq));
    }
  }

  // Colorway color-tag aliases — EXACT match only
  if (report.match_type === "EXACT" && colorwayName) {
    const cwAnchor = norm(colorwayName).split(" ")[0];
    if (cwAnchor && norm(modelname).includes(cwAnchor)) {
      CJK.lastIndex = 0;
      const seqs = (modelname.match(CJK) ?? []).filter((s) => s.length >= 2);
      for (const seq of seqs) {
        writes.push(upsertColorwayAlias(brand, productLine, colorwayName, seq));
      }
    }
  }

  if (writes.length > 0) {
    await Promise.all(writes);
  }
}
