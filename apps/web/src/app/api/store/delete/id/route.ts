import { NextRequest, NextResponse } from "next/server";
import { Client } from "@langchain/langgraph-sdk";
import { LANGGRAPH_API_URL } from "@/constants";

export async function POST(req: NextRequest) {
  // Authentication disabled - allow all requests

  const { namespace, key, id } = await req.json();

  const lgClient = new Client({
    apiKey: process.env.LANGCHAIN_API_KEY,
    apiUrl: LANGGRAPH_API_URL,
  });

  try {
    const currentItems = await lgClient.store.getItem(namespace, key);
    if (!currentItems?.value) {
      return new NextResponse(
        JSON.stringify({
          error: "Item not found",
          success: false,
        }),
        {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    const newValues = Object.fromEntries(
      Object.entries(currentItems.value).filter(([k]) => k !== id)
    );

    await lgClient.store.putItem(namespace, key, newValues);

    return new NextResponse(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (_) {
    return new NextResponse(
      JSON.stringify({ error: "Failed to share run after multiple attempts." }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}
