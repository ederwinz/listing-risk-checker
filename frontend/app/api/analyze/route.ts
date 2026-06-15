import { NextRequest, NextResponse } from "next/server";
import { extractFromImage, fileToBase64 } from "@/lib/extraction";
import { loadAllVerified, loadAliases } from "@/lib/supabase";
import { runComparison } from "@/lib/comparison";
import { tryLogAlias } from "@/lib/alias-logger";

export const maxDuration = 60;

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const imageFile = formData.get("image") as File | null;

    if (!imageFile) {
      return NextResponse.json({ error: "No image provided" }, { status: 400 });
    }

    const buffer = await imageFile.arrayBuffer();
    const { data: imageBase64, mediaType } = fileToBase64(buffer, imageFile.name);

    const [extracted, reference, aliasData] = await Promise.all([
      extractFromImage(imageBase64, mediaType),
      loadAllVerified(),
      loadAliases(),
    ]);

    const report = runComparison(extracted, reference, aliasData);

    // Fire-and-forget — non-blocking, non-fatal
    tryLogAlias(extracted, report).catch(() => {});

    return NextResponse.json(report);
  } catch (err) {
    console.error("/api/analyze error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Analysis failed" },
      { status: 500 }
    );
  }
}
