import { FASTAPI_API_URL } from "@/constants";
import { GraphInput } from "@/shared/types";

export interface FastAPIRequest {
  messages: any[];
  artifact?: any;
  config?: {
    configurable?: Record<string, any>;
  };
}

export interface FastAPIResponse {
  messages?: any[];
  artifact?: any;
  [key: string]: any;
}

/**
 * Call FastAPI agent endpoint
 */
export async function callFastAPIAgent(
  input: GraphInput,
  config?: { configurable?: Record<string, any> }
): Promise<FastAPIResponse> {
  const requestBody: FastAPIRequest = {
    messages: input.messages || [],
    artifact: input.artifact,
    config: {
      configurable: {
        ...config?.configurable,
        customModelName: (config?.configurable as any)?.customModelName,
        modelConfig: (config?.configurable as any)?.modelConfig,
      },
    },
  };

  const response = await fetch(`${FASTAPI_API_URL}/api/agent/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`FastAPI request failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call FastAPI reflection endpoint
 */
export async function callFastAPIReflection(
  messages: any[],
  artifact?: any,
  config?: { configurable?: Record<string, any> }
): Promise<FastAPIResponse> {
  const requestBody: FastAPIRequest = {
    messages,
    artifact,
    config,
  };

  const response = await fetch(`${FASTAPI_API_URL}/api/reflection/reflect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`FastAPI reflection failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call FastAPI thread title generation endpoint
 */
export async function callFastAPIThreadTitle(
  messages: any[],
  artifact?: any,
  config?: { configurable?: Record<string, any> }
): Promise<FastAPIResponse> {
  const requestBody: FastAPIRequest = {
    messages,
    artifact,
    config,
  };

  const response = await fetch(`${FASTAPI_API_URL}/api/thread-title/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`FastAPI thread title failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call FastAPI summarizer endpoint
 */
export async function callFastAPISummarizer(
  messages: any[],
  threadId: string,
  config?: { configurable?: Record<string, any> }
): Promise<FastAPIResponse> {
  const requestBody = {
    messages,
    threadId,
    config,
  };

  const response = await fetch(`${FASTAPI_API_URL}/api/summarizer/summarize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`FastAPI summarizer failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call FastAPI web search endpoint
 */
export async function callFastAPIWebSearch(
  messages: any[],
  config?: { configurable?: Record<string, any> }
): Promise<FastAPIResponse> {
  const requestBody: FastAPIRequest = {
    messages,
    config,
  };

  const response = await fetch(`${FASTAPI_API_URL}/api/web-search/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`FastAPI web search failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Stream FastAPI agent events
 */
export async function* streamFastAPIAgent(
  input: GraphInput,
  config?: { configurable?: Record<string, any> }
): AsyncGenerator<any, void, unknown> {
  const requestBody: FastAPIRequest = {
    messages: input.messages || [],
    artifact: input.artifact,
    config: {
      configurable: {
        ...config?.configurable,
        customModelName: (config?.configurable as any)?.customModelName,
        modelConfig: (config?.configurable as any)?.modelConfig,
      },
    },
  };

  const response = await fetch(`${FASTAPI_API_URL}/api/agent/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`FastAPI stream failed: ${response.status} ${errorText}`);
  }

  if (!response.body) {
    throw new Error("Response body is null");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6); // Remove "data: " prefix
          
          if (data === "[DONE]") {
            return;
          }

          try {
            const event = JSON.parse(data);
            yield event;
          } catch (e) {
            console.error("Failed to parse SSE data:", data, e);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

