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

// Cache for 1 hour — reference database changes only when scrapers run
export const loadAllVerified = unstable_cache(_loadAllVerified, ["verified-products"], {
  revalidate: 3600,
});
