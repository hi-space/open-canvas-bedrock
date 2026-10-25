import { API_URL } from "../../../constants";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const response = await fetch(`${API_URL}/health`, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(2000),
    });
    if (response.ok && (await response.json()).status === "healthy") {
      return Response.json(
        { status: "healthy" },
        { headers: { "Cache-Control": "no-store" } }
      );
    }
  } catch {
    // Failed connections and timeouts make the whole task unavailable.
  }

  return Response.json(
    { status: "unhealthy" },
    { status: 503, headers: { "Cache-Control": "no-store" } }
  );
}
