import Anthropic from "@anthropic-ai/sdk";
import type { Extracted } from "@/types/report";

const EXTRACTION_PROMPT = `You are extracting structured product listing data from a marketplace screenshot.
The listing may be from Rednote (小红书), Taobao (淘宝), Xianyu (闲鱼), or another Chinese e-commerce platform.

Extract the following fields and return ONLY a valid JSON object — no explanation, no markdown fences.
Use null for any field you cannot determine. Preserve Chinese text exactly as shown.

Platform detection hints:
- Rednote (小红书): red header bar, red logo, note/post style layout, heart icons
- Taobao (淘宝): orange branding, shopping cart icon, 淘宝 text visible
- Xianyu (闲鱼): secondhand/resale layout, 闲鱼 text, fish logo, blue/teal accents
- Tmall (天猫): black cat logo, premium store layout
- JD (京东): red JD logo

{
  "platform": "App/platform name in English (Rednote, Taobao, Xianyu, Tmall, JD, WeChat, etc.)",
  "seller_name": "Seller or shop name exactly as displayed (preserve Chinese characters)",
  "listing_title": "Core product description only — strip brand name if it duplicates claimed_brand, remove 【】brackets and marketing filler words, keep the descriptive product name in original language",
  "claimed_brand": "Brand being sold (e.g. Owala, Stanley, Lululemon) — English name",
  "claimed_productline": "Product family/line name (e.g. Freesip, Quencher, Define jacket)",
  "claimed_modelname": "The FULL verbose product name string the seller uses, often in Chinese — this is different from claimed_productline. Example: 'Freesip304双饮保温杯吸管不锈钢水杯'. Include it even if it partially overlaps with claimed_productline.",
  "claimed_size": "Size shown (e.g. 24 oz, 945 ml, 1L, 32oz)",
  "claimed_colorway": "Color or colorway name. Check ALL of these locations: (1) any 'Selected:' or '已选:' field which shows the currently chosen variant — this is the most reliable source, extract the name in parentheses if present e.g. 'Selected: 元气粉(Bunny Business)16oz' → 'Bunny Business', (2) color selector buttons or swatches with text labels, (3) product title, (4) description or SKU strings. If no official color name exists anywhere, describe the visual color from the product photo (e.g. 'light blue', 'sage green'). Only use null if the product truly has no color variant.",
  "claimed_status": "ongoing, special edition, limited edition, collab, discontinued, or unknown",
  "main_colors": "Comma-separated visual colors visible in product photos (e.g. pink, white, sage green)",
  "seller_claims": "Any special claims: official store, authentic, Japan limited, collab with X, global exclusive, etc. null if none.",
  "listing_description": "Key text from the description if visible, truncated to 200 chars"
}`;

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function extractFromImage(imageBase64: string, mediaType: string): Promise<Extracted> {
  const message = await client.messages.create({
    model: "claude-haiku-4-5-20251001",
    max_tokens: 1024,
    messages: [
      {
        role: "user",
        content: [
          {
            type: "image",
            source: { type: "base64", media_type: mediaType as "image/jpeg" | "image/png" | "image/gif" | "image/webp", data: imageBase64 },
          },
          { type: "text", text: EXTRACTION_PROMPT },
        ],
      },
    ],
  });

  const text = message.content[0].type === "text" ? message.content[0].text : "";
  const cleaned = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```\s*$/i, "").trim();
  const raw = JSON.parse(cleaned);

  return {
    claimed_brand: raw.claimed_brand ?? "",
    claimed_productline: raw.claimed_productline ?? "",
    claimed_colorway: raw.claimed_colorway ?? "",
    claimed_size: raw.claimed_size ?? "",
    claimed_status: raw.claimed_status ?? "unknown",
    platform: raw.platform ?? "Unknown",
    seller_name: raw.seller_name ?? "",
    seller_claims: raw.seller_claims ?? "",
  };
}

export function fileToBase64(buffer: ArrayBuffer, filename: string): { data: string; mediaType: string } {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "jpg";
  const mediaTypeMap: Record<string, string> = {
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    png: "image/png",
    gif: "image/gif",
    webp: "image/webp",
  };
  const mediaType = mediaTypeMap[ext] ?? "image/jpeg";
  const data = Buffer.from(buffer).toString("base64");
  return { data, mediaType };
}
