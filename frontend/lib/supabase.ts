import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { unstable_cache } from "next/cache";
import type { VerifiedProduct } from "@/types/report";

let _client: SupabaseClient | null = null;

function getClient(): SupabaseClient {
  if (!_client) {
    const url = process.env.SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_KEY;
    if (!url || !key) throw new Error("Supabase env vars not set (SUPABASE_URL, SUPABASE_SERVICE_KEY)");
    _client = createClient(url, key);
  }
  return _client;
}

async function _loadAllVerified(): Promise<VerifiedProduct[]> {
  const allRows: VerifiedProduct[] = [];
  let offset = 0;

  while (true) {
    const { data, error } = await getClient()
      .from("verified_products")
      .select("item_id,brand,product_line,model_name,colorway_name,sizes_available,status,price,sale_price,screenshot_url,source_url")
      .range(offset, offset + 999);

    if (error) throw new Error(`Supabase error: ${error.message}`);
    if (!data || data.length === 0) break;

    allRows.push(...(data as VerifiedProduct[]));
    if (data.length < 1000) break;
    offset += 1000;
  }

  return allRows;
}

// Keep an in-memory copy for 1 hour so we don't re-fetch all ~10k rows on every request.
// We can't use Next's unstable_cache here: it rejects items over 2MB, and this dataset is ~5MB.
let _verifiedCache: { data: VerifiedProduct[]; at: number } | null = null;
const VERIFIED_TTL_MS = 3_600_000; // 1 hour

export async function loadAllVerified(): Promise<VerifiedProduct[]> {
  if (_verifiedCache && Date.now() - _verifiedCache.at < VERIFIED_TTL_MS) {
    return _verifiedCache.data;
  }
  const data = await _loadAllVerified();
  _verifiedCache = { data, at: Date.now() };
  return data;
}

// ── Aliases ───────────────────────────────────────────────────────────────────

export type AliasData = Record<string, Record<string, {
  aliases: string[];
  colorways: Record<string, string[]>;
}>>;

async function _loadAliases(): Promise<AliasData> {
  const [{ data: plRows, error: plErr }, { data: cwRows, error: cwErr }] = await Promise.all([
    getClient().from("product_line_aliases").select("brand,product_line,alias"),
    getClient().from("colorway_aliases").select("brand,product_line,colorway_name,color_tag"),
  ]);
  if (plErr) throw new Error(`Supabase error (product_line_aliases): ${plErr.message}`);
  if (cwErr) throw new Error(`Supabase error (colorway_aliases): ${cwErr.message}`);
  const result: AliasData = {};
  for (const row of plRows ?? []) {
    (result[row.brand] ??= {})[row.product_line] ??= { aliases: [], colorways: {} };
    result[row.brand][row.product_line].aliases.push(row.alias);
  }
  for (const row of cwRows ?? []) {
    (result[row.brand] ??= {})[row.product_line] ??= { aliases: [], colorways: {} };
    (result[row.brand][row.product_line].colorways[row.colorway_name] ??= []).push(row.color_tag);
  }
  return result;
}

export const loadAliases = unstable_cache(_loadAliases, ["aliases"], { revalidate: 3600 });

export async function upsertProductLineAlias(brand: string, productLine: string, alias: string): Promise<void> {
  try {
    await getClient()
      .from("product_line_aliases")
      .upsert({ brand, product_line: productLine, alias }, { onConflict: "brand,product_line,alias", ignoreDuplicates: true })
      .throwOnError();
  } catch { /* non-fatal */ }
}

export async function upsertColorwayAlias(
  brand: string, productLine: string, colorwayName: string, colorTag: string
): Promise<void> {
  try {
    await getClient()
      .from("colorway_aliases")
      .upsert(
        { brand, product_line: productLine, colorway_name: colorwayName, color_tag: colorTag },
        { onConflict: "brand,product_line,colorway_name,color_tag", ignoreDuplicates: true }
      )
      .throwOnError();
  } catch { /* non-fatal */ }
}
