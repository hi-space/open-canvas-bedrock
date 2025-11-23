import { NextRequest, NextResponse } from "next/server";
import { API_URL } from "@/constants";

export async function POST(req: NextRequest) {
  // Authentication disabled - allow all requests

  const body = await req.json();

  try {
    const response = await fetch(`${API_URL}/api/store/get`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new NextResponse(
        JSON.stringify({ error: errorText || "Failed to get store item" }),
        {
          status: response.status,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    const data = await response.json();
    return new NextResponse(JSON.stringify(data), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e: any) {
    return new NextResponse(
      JSON.stringify({ error: e.message || "Failed to get store item" }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}
