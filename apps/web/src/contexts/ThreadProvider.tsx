import {
  ALL_MODEL_NAMES,
  ALL_MODELS,
  DEFAULT_MODEL_CONFIG,
  DEFAULT_MODEL_NAME,
} from "@/shared/models";
import { CustomModelConfig } from "@/shared/types";
import { Thread } from "@langchain/langgraph-sdk";
import { createContext, ReactNode, useContext, useMemo, useState } from "react";
import { useUserContext } from "./UserContext";
import { useToast } from "@/hooks/use-toast";
import { useQueryState } from "nuqs";
import { API_URL } from "@/constants";

type ThreadContentType = {
  threadId: string | null;
  userThreads: Thread[];
  isUserThreadsLoading: boolean;
  modelName: ALL_MODEL_NAMES;
  modelConfig: CustomModelConfig;
  modelConfigs: Record<ALL_MODEL_NAMES, CustomModelConfig>;
  createThreadLoading: boolean;
  getThread: (id: string) => Promise<Thread | undefined>;
  createThread: () => Promise<Thread | undefined>;
  getUserThreads: () => Promise<void>;
  deleteThread: (id: string, clearMessages: () => void) => Promise<void>;
  setThreadId: (id: string | null) => void;
  setModelName: (name: ALL_MODEL_NAMES) => void;
  setModelConfig: (
    modelName: ALL_MODEL_NAMES,
    config: CustomModelConfig
  ) => void;
};

const ThreadContext = createContext<ThreadContentType | undefined>(undefined);

export function ThreadProvider({ children }: { children: ReactNode }) {
  const { user } = useUserContext();
  const { toast } = useToast();
  const [threadId, setThreadId] = useQueryState("threadId");
  const [userThreads, setUserThreads] = useState<Thread[]>([]);
  const [isUserThreadsLoading, setIsUserThreadsLoading] = useState(false);
  const [modelName, setModelName] =
    useState<ALL_MODEL_NAMES>(DEFAULT_MODEL_NAME);
  const [createThreadLoading, setCreateThreadLoading] = useState(false);

  const [modelConfigs, setModelConfigs] = useState<
    Record<ALL_MODEL_NAMES, CustomModelConfig>
  >(() => {
    // Initialize with default configs for all models
    const initialConfigs: Record<ALL_MODEL_NAMES, CustomModelConfig> =
      {} as Record<ALL_MODEL_NAMES, CustomModelConfig>;

    ALL_MODELS.forEach((model) => {
      const modelKey = model.modelName || model.name;

      initialConfigs[modelKey] = {
        ...model.config,
        provider: model.config.provider,
        temperatureRange: {
          ...(model.config.temperatureRange ||
            DEFAULT_MODEL_CONFIG.temperatureRange),
        },
        maxTokens: {
          ...(model.config.maxTokens || DEFAULT_MODEL_CONFIG.maxTokens),
        },
        ...(model.config.provider === "azure_openai" && {
          azureConfig: {
            azureOpenAIApiKey: process.env._AZURE_OPENAI_API_KEY || "",
            azureOpenAIApiInstanceName:
              process.env._AZURE_OPENAI_API_INSTANCE_NAME || "",
            azureOpenAIApiDeploymentName:
              process.env._AZURE_OPENAI_API_DEPLOYMENT_NAME || "",
            azureOpenAIApiVersion:
              process.env._AZURE_OPENAI_API_VERSION || "2024-08-01-preview",
            azureOpenAIBasePath: process.env._AZURE_OPENAI_API_BASE_PATH,
          },
        }),
      };
    });
    return initialConfigs;
  });

  const modelConfig = useMemo(() => {
    // Try exact match first, then try without "azure/" or "groq/" prefixes
    const config = 
      modelConfigs[modelName] || 
      modelConfigs[modelName.replace("azure/", "")] ||
      modelConfigs[modelName.replace("groq/", "")] ||
      DEFAULT_MODEL_CONFIG;
    return config;
  }, [modelName, modelConfigs]);

  const setModelConfig = (
    modelName: ALL_MODEL_NAMES,
    config: CustomModelConfig
  ) => {
    setModelConfigs((prevConfigs) => {
      if (!config || !modelName) {
        return prevConfigs;
      }
      return {
        ...prevConfigs,
        [modelName]: {
          ...config,
          provider: config.provider,
          temperatureRange: {
            ...(config.temperatureRange ||
              DEFAULT_MODEL_CONFIG.temperatureRange),
          },
          maxTokens: {
            ...(config.maxTokens || DEFAULT_MODEL_CONFIG.maxTokens),
          },
          ...(config.provider === "azure_openai" && {
            azureConfig: {
              ...config.azureConfig,
              azureOpenAIApiKey:
                config.azureConfig?.azureOpenAIApiKey ||
                process.env._AZURE_OPENAI_API_KEY ||
                "",
              azureOpenAIApiInstanceName:
                config.azureConfig?.azureOpenAIApiInstanceName ||
                process.env._AZURE_OPENAI_API_INSTANCE_NAME ||
                "",
              azureOpenAIApiDeploymentName:
                config.azureConfig?.azureOpenAIApiDeploymentName ||
                process.env._AZURE_OPENAI_API_DEPLOYMENT_NAME ||
                "",
              azureOpenAIApiVersion:
                config.azureConfig?.azureOpenAIApiVersion ||
                "2024-08-01-preview",
              azureOpenAIBasePath:
                config.azureConfig?.azureOpenAIBasePath ||
                process.env._AZURE_OPENAI_API_BASE_PATH,
            },
          }),
        },
      };
    });
  };

  const createThread = async (): Promise<Thread | undefined> => {
    // Authentication disabled - allow thread creation without user
    setCreateThreadLoading(true);

    try {
      const response = await fetch(`${API_URL}/threads`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          metadata: {
            customModelName: modelName,
            modelConfig: {
              ...modelConfig,
              // Ensure Azure config is included if needed
              ...(modelConfig.provider === "azure_openai" && {
                azureConfig: modelConfig.azureConfig,
              }),
            },
          },
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create thread: ${response.statusText}`);
      }

      const thread = await response.json();
      setThreadId(thread.thread_id);
      // Fetch updated threads so the new thread is included.
      // Do not await since we do not want to block the UI.
      // Silently fail if getUserThreads fails
      getUserThreads().catch((e) => {
        console.warn("Failed to refresh thread list after creation:", e);
      });
      return thread;
    } catch (e) {
      console.error("Failed to create thread", e);
      toast({
        title: "Failed to create thread",
        description:
          "An error occurred while trying to create a new thread. Please try again.",
        duration: 5000,
        variant: "destructive",
      });
    } finally {
      setCreateThreadLoading(false);
    }
  };

  const getUserThreads = async () => {
    // Authentication disabled - get all threads without user filter
    setIsUserThreadsLoading(true);
    try {
      // Search without user filter - get all threads
      // If search fails (e.g., no threads exist), return empty array
      try {
        const response = await fetch(`${API_URL}/threads/search`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            limit: 100,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to search threads: ${response.statusText}`);
        }

        const userThreads = await response.json();
        if (Array.isArray(userThreads) && userThreads.length > 0) {
          const lastInArray = userThreads[0];
          const allButLast = userThreads.slice(1, userThreads.length);
          const filteredThreads = allButLast.filter(
            (thread) => thread.values && Object.keys(thread.values).length > 0
          );
          setUserThreads([...filteredThreads, lastInArray]);
        } else {
          setUserThreads([]);
        }
      } catch (searchError) {
        // If search fails (404 or other errors), just set empty array
        console.warn("Failed to search threads, returning empty list:", searchError);
        setUserThreads([]);
      }
    } catch (e) {
      console.error("Error in getUserThreads:", e);
      setUserThreads([]);
    } finally {
      setIsUserThreadsLoading(false);
    }
  };

  const deleteThread = async (id: string, clearMessages: () => void) => {
    setUserThreads((prevThreads) => {
      const newThreads = prevThreads.filter(
        (thread) => thread.thread_id !== id
      );
      return newThreads;
    });
    if (id === threadId) {
      clearMessages();
      // Create a new thread. Use .then to avoid blocking the UI.
      // Once completed, `createThread` will re-fetch all user
      // threads to update UI.
      void createThread();
    }
    try {
      const response = await fetch(`${API_URL}/threads/${id}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(`Failed to delete thread: ${response.statusText}`);
      }
    } catch (e) {
      console.error(`Failed to delete thread with ID ${id}`, e);
    }
  };

  const getThread = async (id: string): Promise<Thread | undefined> => {
    try {
      const response = await fetch(`${API_URL}/threads/${id}`, {
        method: "GET",
      });
      if (!response.ok) {
        throw new Error(`Failed to get thread: ${response.statusText}`);
      }
      return await response.json();
    } catch (e) {
      console.error("Failed to get thread by ID.", id, e);
      toast({
        title: "Failed to get thread",
        description: "An error occurred while trying to get a thread.",
        duration: 5000,
        variant: "destructive",
      });
    }

    return undefined;
  };

  const contextValue: ThreadContentType = {
    threadId,
    userThreads,
    isUserThreadsLoading,
    modelName,
    modelConfig,
    modelConfigs,
    createThreadLoading,
    getThread,
    createThread,
    getUserThreads,
    deleteThread,
    setThreadId,
    setModelName,
    setModelConfig,
  };

  return (
    <ThreadContext.Provider value={contextValue}>
      {children}
    </ThreadContext.Provider>
  );
}

export function useThreadContext() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreadContext must be used within a ThreadProvider");
  }
  return context;
}
