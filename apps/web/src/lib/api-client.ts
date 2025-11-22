import { API_URL } from "@/constants";
import { GraphInput } from "@/shared/types";

export interface ApiRequest {
  messages: any[];
  artifact?: any;
  config?: {
    configurable?: Record<string, any>;
  };
}

export interface ApiResponse {
  messages?: any[];
  artifact?: any;
  [key: string]: any;
}

/**
 * Call agent endpoint
 */
export async function callAgent(
  input: GraphInput,
  config?: { configurable?: Record<string, any> }
): Promise<ApiResponse> {
  const requestBody: ApiRequest = {
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

  const response = await fetch(`${API_URL}/api/agent/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Request failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call reflection endpoint
 */
export async function callReflection(
  messages: any[],
  artifact?: any,
  config?: { configurable?: Record<string, any> }
): Promise<ApiResponse> {
  const requestBody: ApiRequest = {
    messages,
    artifact,
    config: {
      configurable: {
        ...config?.configurable,
        customModelName: (config?.configurable as any)?.customModelName,
        modelConfig: (config?.configurable as any)?.modelConfig,
      },
    },
  };

  const response = await fetch(`${API_URL}/api/reflection/reflect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Reflection failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call thread title generation endpoint
 */
export async function callThreadTitle(
  messages: any[],
  artifact?: any,
  config?: { configurable?: Record<string, any> }
): Promise<ApiResponse> {
  const requestBody: ApiRequest = {
    messages,
    artifact,
    config: {
      configurable: {
        ...config?.configurable,
        customModelName: (config?.configurable as any)?.customModelName,
        modelConfig: (config?.configurable as any)?.modelConfig,
      },
    },
  };

  const response = await fetch(`${API_URL}/api/thread-title/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Thread title failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call summarizer endpoint
 */
export async function callSummarizer(
  messages: any[],
  threadId: string,
  config?: { configurable?: Record<string, any> }
): Promise<ApiResponse> {
  const requestBody = {
    messages,
    threadId,
    config: {
      configurable: {
        ...config?.configurable,
        customModelName: (config?.configurable as any)?.customModelName,
        modelConfig: (config?.configurable as any)?.modelConfig,
      },
    },
  };

  const response = await fetch(`${API_URL}/api/summarizer/summarize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Summarizer failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Call web search endpoint
 */
export async function callWebSearch(
  messages: any[],
  config?: { configurable?: Record<string, any> }
): Promise<ApiResponse> {
  const requestBody: ApiRequest = {
    messages,
    config: {
      configurable: {
        ...config?.configurable,
        customModelName: (config?.configurable as any)?.customModelName,
        modelConfig: (config?.configurable as any)?.modelConfig,
      },
    },
  };

  const response = await fetch(`${API_URL}/api/web-search/search`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Web search failed: ${response.status} ${errorText}`);
  }

  return await response.json();
}

/**
 * Stream agent events
 */
export async function* streamAgent(
  input: GraphInput,
  config?: { configurable?: Record<string, any> }
): AsyncGenerator<any, void, unknown> {
  // Ensure customModelName and modelConfig are always present
  const configurable = {
    ...config?.configurable,
    customModelName: (config?.configurable as any)?.customModelName,
    modelConfig: (config?.configurable as any)?.modelConfig,
  };
  
  // Debug logging
  if (!configurable.customModelName) {
    console.error("ERROR: customModelName is missing in config!", {
      config,
      configurable,
    });
  }
  
  const requestBody: ApiRequest = {
    messages: input.messages || [],
    artifact: input.artifact,
    config: {
      configurable: configurable,
    },
  };

  const response = await fetch(`${API_URL}/api/agent/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Stream failed: ${response.status} ${errorText}`);
  }

  if (!response.body) {
    throw new Error("Response body is null");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventCount = 0;

  try {
    console.log("Starting to read stream...");
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) {
        console.log(`Stream ended. Total events received: ${eventCount}`);
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.trim() === "") continue; // Skip empty lines
        
        if (line.startsWith("data: ")) {
          const data = line.slice(6); // Remove "data: " prefix
          
          if (data === "[DONE]") {
            console.log("Received [DONE] signal");
            return;
          }

          try {
            const event = JSON.parse(data);
            eventCount++;
            const eventType = event?.event || "unknown";
            const eventName = event?.name || "unknown";
            console.log(`Received event #${eventCount}: ${eventType} from ${eventName}`, event);
            yield event;
          } catch (e) {
            console.error("Failed to parse SSE data:", data, e);
          }
        } else {
          console.warn("Received non-SSE line:", line);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

