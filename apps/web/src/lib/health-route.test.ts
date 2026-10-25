import { createServer, type RequestListener, type Server } from "node:http";
import { afterEach, describe, expect, it, vi } from "vitest";

let backend: Server | undefined;

afterEach(async () => {
  vi.unstubAllEnvs();
  if (backend) {
    backend.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      backend!.close((error) => (error ? reject(error) : resolve()))
    );
    backend = undefined;
  }
});

async function startBackend(handler: RequestListener) {
  backend = createServer(handler);
  await new Promise<void>((resolve) =>
    backend!.listen(0, "127.0.0.1", resolve)
  );
  const address = backend.address();
  if (!address || typeof address === "string")
    throw new Error("No backend port");
  vi.stubEnv("API_URL", `http://127.0.0.1:${address.port}`);
  vi.resetModules();
  return import("../app/api/health/route");
}

describe("deployment health", () => {
  it("reports healthy only after checking the backend health endpoint", async () => {
    const { GET } = await startBackend((request, response) => {
      response.writeHead(request.url === "/health" ? 200 : 404, {
        "Content-Type": "application/json",
      });
      response.end(JSON.stringify({ status: "healthy" }));
    });

    const response = await GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "healthy" });
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });

  it("reports unavailable when the backend health endpoint fails", async () => {
    const { GET } = await startBackend((_request, response) => {
      response.writeHead(503);
      response.end(JSON.stringify({ status: "unhealthy" }));
    });

    expect((await GET()).status).toBe(503);
  });

  it("rejects an unsuccessful health payload even with HTTP 200", async () => {
    const { GET } = await startBackend((_request, response) => {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ status: "unhealthy" }));
    });

    expect((await GET()).status).toBe(503);
  });

  it("reports unavailable when the backend connection is refused", async () => {
    const { GET } = await startBackend((_request, response) => response.end());
    await new Promise<void>((resolve) => backend!.close(() => resolve()));
    backend = undefined;

    expect((await GET()).status).toBe(503);
  });

  it("bounds a backend that accepts a connection but never responds", async () => {
    const { GET } = await startBackend(() => {});
    const started = performance.now();

    expect((await GET()).status).toBe(503);
    expect(performance.now() - started).toBeLessThan(3500);
  }, 5000);
});
