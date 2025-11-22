import { createServerClient } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";

export async function updateSession(request: NextRequest) {
  // Authentication disabled - allow all requests
    return NextResponse.next({ request });
}
