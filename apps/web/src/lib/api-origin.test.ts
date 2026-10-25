import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv("API_URL", undefined);
  vi.stubEnv("FASTAPI_API_URL", undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("API request origin", () => {
  it("sends browser requests through the current origin even with an internal API configured", async () => {
    vi.stubGlobal("window", {
      location: { origin: "https://canvas.example.test" },
    });
    vi.stubEnv("API_URL", "http://127.0.0.1:9000");
    const { API_URL } = await import("../constants");

    expect(`${API_URL}/api/models/list`).toBe(
      "https://canvas.example.test/api/models/list"
    );
  });

  it("uses API_URL for server requests before FASTAPI_API_URL", async () => {
    vi.stubEnv("API_URL", "http://primary:9000");
    vi.stubEnv("FASTAPI_API_URL", "http://fallback:9000");
    const { API_URL } = await import("../constants");

    expect(`${API_URL}/api/threads`).toBe("http://primary:9000/api/threads");
  });

  it("uses FASTAPI_API_URL for server requests when API_URL is absent", async () => {
    vi.stubEnv("FASTAPI_API_URL", "http://fallback:9000");
    const { API_URL } = await import("../constants");

    expect(`${API_URL}/api/threads`).toBe("http://fallback:9000/api/threads");
  });

  it("uses the task-local backend for server requests without configuration", async () => {
    const { API_URL } = await import("../constants");

    expect(`${API_URL}/api/threads`).toBe("http://localhost:9000/api/threads");
  });
});
