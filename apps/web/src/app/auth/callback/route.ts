import { NextResponse } from "next/server";

export async function GET(request: Request) {
  // Authentication disabled
  const { origin } = new URL(request.url);
  return NextResponse.redirect(`${origin}/auth/auth-code-error`);
}
