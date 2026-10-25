import { describe, expect, it } from "vitest";
import { backendHeaders } from "./workspace-proxy";

describe("workspace authentication forwarding", () => {
  it("forwards only the ALB signed identity, not caller-selected ownership or cookies", () => {
    const headers = backendHeaders(new Headers({
      "x-amzn-oidc-data": "signed-alb-token",
      "x-workspace-owner": "attacker",
      authorization: "Bearer attacker",
      cookie: "private-session",
    }));
    expect(headers.get("x-amzn-oidc-data")).toBe("signed-alb-token");
    expect(headers.get("x-workspace-owner")).toBeNull();
    expect(headers.get("authorization")).toBeNull();
    expect(headers.get("cookie")).toBeNull();
  });
  it("does not manufacture identity for an unauthenticated request", () => {
    expect(backendHeaders(new Headers()).get("x-amzn-oidc-data")).toBeNull();
  });
});
