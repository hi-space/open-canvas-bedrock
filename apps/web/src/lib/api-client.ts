import { API_URL } from "@/constants";
import { GraphInput, ModelConfigurationParams, CustomModelConfig } from "@/shared/types";

export interface ApiRequest {
  messages: any[];
  artifact?: any;
  language?: string;
  artifactLength?: string;
  regenerateWithEmojis?: boolean;
  readingLevel?: string;
  highlightedText?: any;
  customQuickActionId?: string;
  webSearchEnabled?: boolean;
  webSearchResults?: any[];
  next?: string;
  config?: {
    configurable?: Record<string, any>;
  };
}

export interface ApiResponse {
  messages?: any[];
  artifact?: any;
  [key: string]: any;
}

export interface ModelsResponse {
  models: ModelConfigurationParams[];
  defaultModelName: string;
  defaultModelConfig: CustomModelConfig;
}

/**
 * Fetch available models from the backend
 */
export async function fetchModels(): Promise<ModelsResponse> {
  const response = await fetch(`${API_URL}/api/models/list`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Failed to fetch models: ${response.status} ${errorText}`);
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

  console.log("[callReflection] Request body:", JSON.stringify(requestBody, null, 2));

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

  console.log("[callThreadTitle] Request body:", JSON.stringify(requestBody, null, 2));

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

  console.log("[callSummarizer] Request body:", JSON.stringify(requestBody, null, 2));

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

  console.log("[callWebSearch] Request body:", JSON.stringify(requestBody, null, 2));

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
    // Include all rewrite-related fields
    language: input.language,
    artifactLength: input.artifactLength,
    regenerateWithEmojis: input.regenerateWithEmojis,
    readingLevel: input.readingLevel,
    highlightedText: input.highlightedText,
    customQuickActionId: input.customQuickActionId,
    webSearchEnabled: input.webSearchEnabled,
    webSearchResults: input.webSearchResults,
    next: input.next,
    config: {
      configurable: configurable,
    },
  };

  // Debug logging for rewrite-related fields
  console.log("[streamAgent] Request body fields:", {
    language: requestBody.language,
    artifactLength: requestBody.artifactLength,
    regenerateWithEmojis: requestBody.regenerateWithEmojis,
    readingLevel: requestBody.readingLevel,
    highlightedText: requestBody.highlightedText,
    customQuickActionId: requestBody.customQuickActionId,
    webSearchEnabled: requestBody.webSearchEnabled,
    hasMessages: (requestBody.messages?.length || 0) > 0,
    hasArtifact: !!requestBody.artifact,
  });

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
