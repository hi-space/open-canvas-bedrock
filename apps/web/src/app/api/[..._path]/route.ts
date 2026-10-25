import { API_URL } from "../../../constants";
import { NextRequest, NextResponse } from "next/server";
import { backendHeaders } from "@/lib/workspace-proxy";

function getCorsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
  };
}

async function handleRequest(req: NextRequest, method: string) {
  // ALB authenticates the browser; the workspace backend verifies its signature.
  try {
    // Keep /api/ prefix - pass pathname as-is to backend
    // pathname is like /api/agent/stream, we send /api/agent/stream to backend
    const path = req.nextUrl.pathname;
    const url = new URL(req.url);
    const searchParams = new URLSearchParams(url.search);
    searchParams.delete("_path");
    searchParams.delete("nxtP_path");
    const queryString = searchParams.toString()
      ? `?${searchParams.toString()}`
      : "";

    const outgoingHeaders = backendHeaders(req.headers, process.env.LANGCHAIN_API_KEY);
    const options: RequestInit = {
      method,
      headers: outgoingHeaders,
      cache: "no-store",
    };

    if (["POST", "PUT", "PATCH"].includes(method)) {
      outgoingHeaders.set("Content-Type", "application/json");
      const bodyText = await req.text();
      if (bodyText.length > 2500000) {
        return NextResponse.json({ detail: "요청이 너무 큽니다." }, { status: 413 });
      }

      if (typeof bodyText === "string" && bodyText.length > 0) {
        const parsedBody = JSON.parse(bodyText);
        parsedBody.config = parsedBody.config || {};
        parsedBody.config.configurable = {
          ...parsedBody.config.configurable,
        };
        options.body = JSON.stringify(parsedBody);
      } else {
        options.body = bodyText;
      }
    }

    const res = await fetch(
      `${API_URL}${path}${queryString}`,
      options
    );

    if (res.status >= 400) {
      console.error(
        "ERROR IN PROXY",
        `${API_URL}/${path}${queryString}`,
        res.status,
        res.statusText
      );
      return new Response(res.body, {
        status: res.status,
        statusText: res.statusText,
        headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
      });
    }

    const headers = new Headers({
      ...(path.startsWith("/api/workspaces") ? {} : getCorsHeaders()),
      "Cache-Control": "no-store",
    });
    // Safely add headers from the original response
    res.headers.forEach((value, key) => {
      try {
        headers.set(key, value);
      } catch (error) {
        console.warn(`Failed to set header: ${key}`, error);
      }
    });

    return new Response(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers,
    });
  } catch (e: any) {
    console.error("Error in proxy");
    return NextResponse.json(
      { detail: "서버 요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요." },
      { status: e instanceof SyntaxError ? 400 : 502 }
    );
  }
}

export const GET = (req: NextRequest) => handleRequest(req, "GET");
export const POST = (req: NextRequest) => handleRequest(req, "POST");
export const PUT = (req: NextRequest) => handleRequest(req, "PUT");
export const PATCH = (req: NextRequest) => handleRequest(req, "PATCH");
export const DELETE = (req: NextRequest) => handleRequest(req, "DELETE");

// Add a new OPTIONS handler
export const OPTIONS = () => {
  return new NextResponse(null, {
    status: 204,
    headers: {
      ...getCorsHeaders(),
    },
  });
};
