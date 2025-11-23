import { NextRequest, NextResponse } from "next/server";
import { API_URL } from "@/constants";

export async function POST(req: NextRequest) {
  // Authentication disabled - allow all requests

  const { namespace, key, id } = await req.json();

  try {
    // Get current item
    const getResponse = await fetch(`${API_URL}/store/get`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ namespace, key }),
    });

    if (!getResponse.ok) {
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

    const { item } = await getResponse.json();
    if (!item?.value) {
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

    // Remove the id from the value object
    const newValues = Object.fromEntries(
      Object.entries(item.value).filter(([k]) => k !== id)
    );

    // Update the item
    const putResponse = await fetch(`${API_URL}/store/put`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ namespace, key, value: newValues }),
    });

    if (!putResponse.ok) {
      const errorText = await putResponse.text();
      return new NextResponse(
        JSON.stringify({ error: errorText || "Failed to update store item" }),
        {
          status: putResponse.status,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new NextResponse(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (e: any) {
    return new NextResponse(
      JSON.stringify({ error: e.message || "Failed to delete store item by id" }),
      {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }
    );
  }
}
