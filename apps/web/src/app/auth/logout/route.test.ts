import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST } from "./route";

describe("Cognito logout", () => {
  beforeEach(() => {
    vi.stubEnv("APP_URL", "https://canvas.hi-yoo.com");
    vi.stubEnv(
      "COGNITO_DOMAIN",
      "canvas.auth.ap-northeast-2.amazoncognito.com"
    );
    vi.stubEnv("COGNITO_CLIENT_ID", "public-client-id");
  });
  afterEach(() => vi.unstubAllEnvs());

  it("rejects cross-origin logout requests", async () => {
    const response = await POST(
      new NextRequest("https://canvas.hi-yoo.com/auth/logout", {
        method: "POST",
        headers: { origin: "https://another.example" },
      })
    );
    expect(response.status).toBe(403);
    expect(response.headers.get("location")).toBeNull();
  });

  it("clears every ALB session shard and redirects to the configured Cognito logout", async () => {
    const response = await POST(
      new NextRequest("https://canvas.hi-yoo.com/auth/logout", {
        method: "POST",
        headers: {
          origin: "https://canvas.hi-yoo.com",
          cookie:
            "AWSELBAuthSessionCookie-0=first; AWSELBAuthSessionCookie-1=second; preferences=keep",
        },
      })
    );
    expect(response.status).toBe(303);
    const target = new URL(response.headers.get("location")!);
    expect(target.origin).toBe(
      "https://canvas.auth.ap-northeast-2.amazoncognito.com"
    );
    expect(target.pathname).toBe("/logout");
    expect(target.searchParams.get("client_id")).toBe("public-client-id");
    expect(target.searchParams.get("logout_uri")).toBe(
      "https://canvas.hi-yoo.com/"
    );
    expect(response.cookies.get("AWSELBAuthSessionCookie-0")?.maxAge).toBe(0);
    expect(response.cookies.get("AWSELBAuthSessionCookie-1")?.maxAge).toBe(0);
    expect(response.cookies.get("preferences")).toBeUndefined();
  });

  it("fails closed when production logout configuration is incomplete", async () => {
    vi.stubEnv("COGNITO_CLIENT_ID", "");
    const response = await POST(
      new NextRequest("https://canvas.hi-yoo.com/auth/logout", {
        method: "POST",
        headers: { origin: "https://canvas.hi-yoo.com" },
      })
    );
    expect(response.status).toBe(503);
  });
});
