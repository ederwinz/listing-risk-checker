import { NextRequest, NextResponse } from "next/server";
import { extractFromImage, fileToBase64 } from "@/lib/extraction";
import { loadAllVerified } from "@/lib/supabase";
import { runComparison } from "@/lib/comparison";

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

    const [extracted, reference] = await Promise.all([
      extractFromImage(imageBase64, mediaType),
      loadAllVerified(),
    ]);

    const report = runComparison(extracted, reference);

    return NextResponse.json(report);
  } catch (err) {
    console.error("/api/analyze error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Analysis failed" },
      { status: 500 }
    );
  }
}
