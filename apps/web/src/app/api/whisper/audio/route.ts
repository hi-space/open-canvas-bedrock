import { NextResponse } from "next/server";

export async function POST() {
  // Supabase disabled - audio transcription not available
  return NextResponse.json(
    {
      error: "Audio transcription requires Supabase storage which is not configured.",
    },
    { status: 400 }
  );
}
