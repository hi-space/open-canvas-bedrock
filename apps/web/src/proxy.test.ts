import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

describe("authenticated API origin checks", () => {
  beforeEach(() => {
    vi.stubEnv("COGNITO_DOMAIN", "canvas.auth.ap-northeast-2.amazoncognito.com");
    vi.stubEnv("APP_URL", "https://canvas.hi-yoo.com");
  });
  afterEach(() => vi.unstubAllEnvs());

  it.each([undefined, "https://other.example"])("rejects mutating requests from %s", (origin) => {
    const request = new NextRequest("https://canvas.hi-yoo.com/api/writing/propose", {
      method: "POST", headers: origin ? { origin } : {},
    });
    expect(proxy(request).status).toBe(403);
  });

  it("forwards same-origin writes and ordinary reads", () => {
    for (const request of [
      new NextRequest("https://canvas.hi-yoo.com/api/writing/propose", {
        method: "POST", headers: { origin: "https://canvas.hi-yoo.com" },
      }),
      new NextRequest("https://canvas.hi-yoo.com/api/models/list"),
    ]) {
      expect(proxy(request).headers.get("x-middleware-next")).toBe("1");
    }
  });

  it("keeps unconfigured local development usable", () => {
    vi.stubEnv("COGNITO_DOMAIN", "");
    expect(proxy(new NextRequest("http://localhost:3000/api/writing/propose", {
      method: "POST",
    })).headers.get("x-middleware-next")).toBe("1");
  });
});
