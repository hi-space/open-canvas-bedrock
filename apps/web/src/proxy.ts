import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest): NextResponse {
  if (
    process.env.COGNITO_DOMAIN &&
    !["GET", "HEAD", "OPTIONS"].includes(request.method)
  ) {
    const applicationUrl = process.env.APP_URL;
    if (!applicationUrl) {
      return NextResponse.json({ error: "사이트 인증 설정을 확인해 주세요." }, { status: 503 });
    }
    if (request.headers.get("origin") !== new URL(applicationUrl).origin) {
      return NextResponse.json({ error: "이 사이트에서 요청해 주세요." }, { status: 403 });
    }
  }
  return NextResponse.next();
}

export const config = { matcher: "/api/:path*" };
