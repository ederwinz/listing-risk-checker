export type RiskLevel = "low" | "medium" | "high" | "unverifiable";

export type MatchType =
  | "EXACT"
  | "FUZZY_COLORWAY"
  | "COLORWAY_NOT_FOUND"
  | "PRODUCT_LINE_NOT_FOUND"
  | "BRAND_NOT_FOUND";

export interface Discrepancy {
  field: "colorway" | "status" | "size";
  severity: "medium" | "high";
  message: string;
}

export interface MatchContext {
  brand_count?: number;
  known_brands?: string[];
  known_product_lines?: string[];
  known_colorways?: string[];
  best_fuzzy_score?: number;
  closest_colorway?: string;
  color_tag_match?: boolean;
}

export interface Extracted {
  claimed_brand: string;
  claimed_productline: string;
  claimed_colorway: string;
  claimed_modelname: string;
  claimed_size: string;
  claimed_status: string;
  platform: string;
  seller_name: string;
  seller_claims: string;
  main_colors: string;
}

export interface Report {
  risk_level: RiskLevel;
  match_type: MatchType;
  expected_matchid: string | null;
  expected_matchconfidence: number;
  mismatch_reasons: string;
  official_screenshot_url: string | null;
  official_source_url: string | null;
  match_context: MatchContext;
  discrepancies: Discrepancy[];
  extracted: Extracted;
  matched_product_line?: string;
  matched_colorway_name?: string;
  overall_score: number;
}

export interface VerifiedProduct {
  item_id: string;
  brand: string;
  product_line: string;
  model_name: string;
  colorway_name: string;
  sizes_available: string;
  status: string;
  price: string;
  sale_price: string;
  screenshot_url: string;
  source_url: string;
}

// One slot in the multi-image results list
export interface ResultSlot {
  id: string;
  file: File;
  previewUrl: string;
  status: "pending" | "loading" | "done" | "error";
  report?: Report;
  error?: string;
}
