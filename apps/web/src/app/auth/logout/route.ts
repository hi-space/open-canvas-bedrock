import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const domain = process.env.COGNITO_DOMAIN;
  const clientId = process.env.COGNITO_CLIENT_ID;
  const applicationUrl = process.env.APP_URL;
  if (!domain || !clientId || !applicationUrl) {
    return NextResponse.json(
      { error: "로그아웃 설정을 확인해 주세요." },
      { status: 503 }
    );
  }

  const application = new URL(applicationUrl);
  if (request.headers.get("origin") !== application.origin) {
    return NextResponse.json(
      { error: "이 사이트에서 로그아웃해 주세요." },
      { status: 403 }
    );
  }

  const target = new URL("/logout", `https://${domain}`);
  target.searchParams.set("client_id", clientId);
  target.searchParams.set("logout_uri", new URL("/", application).href);
  const response = NextResponse.redirect(target, 303);
  response.headers.set("Cache-Control", "no-store");
  const names = new Set([
    "AWSELBAuthSessionCookie",
    ...request.cookies
      .getAll()
      .map((cookie) => cookie.name)
      .filter((name) => /^AWSELBAuthSessionCookie-\d+$/.test(name)),
  ]);
  for (const name of names) {
    response.cookies.set(name, "", {
      httpOnly: true,
      secure: true,
      sameSite: "lax",
      path: "/",
      maxAge: 0,
    });
  }
  return response;
}
