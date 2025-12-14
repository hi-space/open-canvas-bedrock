import { v4 as uuidv4 } from "uuid";
import { useUserContext } from "@/contexts/UserContext";
import {
  isArtifactMarkdownContent,
} from "@/shared/utils/artifacts";
import { reverseCleanContent } from "@/lib/normalize_string";
import {
  Artifact,
  ArtifactType,
  ArtifactMarkdown,
  ArtifactCode,
  CustomModelConfig,
  GraphInput,
  ProgrammingLanguageOptions,
  RewriteArtifactMetaToolResponse,
  SearchResult,
  TextHighlight,
} from "@/shared/types";
import { AIMessage, BaseMessage, HumanMessage } from "@langchain/core/messages";
import { serializeLangChainMessage } from "@/lib/convert_messages";
import { useRuns } from "@/hooks/useRuns";
import { streamAgent } from "@/lib/api-client";
import { WEB_SEARCH_RESULTS_QUERY_PARAM } from "@/constants";
import { API_URL } from "@/constants";
import {
  DEFAULT_INPUTS,
  OC_WEB_SEARCH_RESULTS_MESSAGE_KEY,
} from "@/shared/types";
import {
  ALL_MODEL_NAMES,
  NON_STREAMING_TEXT_MODELS,
  NON_STREAMING_TOOL_CALLING_MODELS,
  DEFAULT_MODEL_CONFIG,
  DEFAULT_MODEL_NAME,
} from "@/shared/models";
import { Thread } from "@langchain/langgraph-sdk";
import { useToast } from "@/hooks/use-toast";
import {
  createContext,
  Dispatch,
  ReactNode,
  SetStateAction,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  extractChunkFields,
  handleGenerateArtifactToolCallChunk,
  removeCodeBlockFormatting,
  replaceOrInsertMessageChunk,
  updateHighlightedMarkdown,
  updateRewrittenArtifact,
} from "./utils";
import {
  handleRewriteArtifactThinkingModel,
  isThinkingModel,
} from "@/shared/utils/thinking";
import { debounce } from "lodash";
import { useThreadContext } from "./ThreadProvider";
import { useAssistantContext } from "./AssistantContext";
import { useQueryState } from "nuqs";

interface GraphData {
  runId: string | undefined;
  isStreaming: boolean;
  isLoadingThread: boolean;
  error: boolean;
  selectedBlocks: TextHighlight | undefined;
  messages: BaseMessage[];
  artifact: Artifact | undefined;
  updateRenderedArtifactRequired: boolean;
  isArtifactSaved: boolean;
  firstTokenReceived: boolean;
  feedbackSubmitted: boolean;
  artifactUpdateFailed: boolean;
  chatStarted: boolean;
  searchEnabled: boolean;
  // Diff comparison mode
  isDiffMode: boolean;
  diffBaseVersionIndex: number | undefined; // Version to compare against (usually previous version)
  setSearchEnabled: Dispatch<SetStateAction<boolean>>;
  setChatStarted: Dispatch<SetStateAction<boolean>>;
  setIsStreaming: Dispatch<SetStateAction<boolean>>;
  setFeedbackSubmitted: Dispatch<SetStateAction<boolean>>;
  setArtifact: Dispatch<SetStateAction<Artifact | undefined>>;
  setSelectedBlocks: Dispatch<SetStateAction<TextHighlight | undefined>>;
  setSelectedArtifact: (index: number) => void;
  setMessages: Dispatch<SetStateAction<BaseMessage[]>>;
  streamMessage: (params: GraphInput) => Promise<void>;
  setArtifactContent: (index: number, content: string) => void;
  clearState: () => void;
  switchSelectedThread: (thread: Thread) => Promise<void>;
  setUpdateRenderedArtifactRequired: Dispatch<SetStateAction<boolean>>;
  setIsDiffMode: Dispatch<SetStateAction<boolean>>;
  setDiffBaseVersionIndex: Dispatch<SetStateAction<number | undefined>>;
  refreshArtifactMetadata: () => Promise<void>; // Refresh version metadata from server
}

type GraphContentType = {
  graphData: GraphData;
};

const GraphContext = createContext<GraphContentType | undefined>(undefined);

// Shim for recent LangGraph bugfix
function extractStreamDataChunk(chunk: any) {
  let result;
  if (Array.isArray(chunk)) {
    result = chunk[1];
  } else {
    result = chunk;
  }
  
  // Ensure the result has the expected structure
  if (result && typeof result === "object") {
    // If it's an AIMessageChunk-like object, ensure it has content
    if (result.content !== undefined && typeof result.content !== "string") {
      // Try to extract string content
      if (Array.isArray(result.content)) {
        // Content might be an array of content blocks
        // ChatBedrockConverse returns: [{'type': 'text', 'text': '...', 'index': 0}]
        const textContent = result.content
          .map((block: any) => {
            if (typeof block === 'string') return block;
            if (typeof block === 'object') {
              // Try different possible field names
              return block.text || block.content || "";
            }
            return "";
          })
          .join("");
        result = { ...result, content: textContent };
      } else {
        result = { ...result, content: String(result.content) };
      }
    }
    
    // Ensure ID exists
    if (!result.id && result.response_metadata?.run_id) {
      result.id = `msg-${result.response_metadata.run_id}`;
    }
    if (!result.id) {
      result.id = `msg-${Date.now()}-${Math.random()}`;
    }
  }
  
  return result;
}

function extractStreamDataOutput(output: any) {
  if (Array.isArray(output)) {
    return output[1];
  }
  return output;
}

export function GraphProvider({ children }: { children: ReactNode }) {
  const userData = useUserContext();
  const assistantsData = useAssistantContext();
  const threadData = useThreadContext();
  const { toast } = useToast();
  const { shareRun } = useRuns();
  const [chatStarted, setChatStarted] = useState(false);
  const [messages, setMessages] = useState<BaseMessage[]>([]);
  const [artifact, setArtifact] = useState<Artifact>();
  const [selectedBlocks, setSelectedBlocks] = useState<TextHighlight>();
  const [isStreaming, setIsStreaming] = useState(false);
  const [updateRenderedArtifactRequired, setUpdateRenderedArtifactRequired] =
    useState(false);
  const lastSavedArtifact = useRef<Artifact | undefined>(undefined);
  const debouncedAPIUpdate = useRef(
    debounce(
      (artifact: Artifact, threadId: string) =>
        updateArtifact(artifact, threadId),
      1500
    )
  ).current;
  const [isArtifactSaved, setIsArtifactSaved] = useState(true);
  const [threadSwitched, setThreadSwitched] = useState(false);
  const [firstTokenReceived, setFirstTokenReceived] = useState(false);
  const [runId, setRunId] = useState<string>();
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [error, setError] = useState(false);
  const [artifactUpdateFailed, setArtifactUpdateFailed] = useState(false);
  const [searchEnabled, setSearchEnabled] = useState(false);
  const [isLoadingThread, setIsLoadingThread] = useState(false);
  const [isDiffMode, setIsDiffMode] = useState(false);
  const [diffBaseVersionIndex, setDiffBaseVersionIndex] = useState<number | undefined>(undefined);

  const [_, setWebSearchResultsId] = useQueryState(
    WEB_SEARCH_RESULTS_QUERY_PARAM
  );

  useEffect(() => {
    // Authentication disabled - allow without user
    if (typeof window === "undefined") return;

    // Load assistants but don't auto-select one
    // User can explicitly choose "No Assistant" or select an assistant
    if (
      !assistantsData.selectedAssistant &&
      !assistantsData.isLoadingAllAssistants &&
      assistantsData.assistants.length === 0
    ) {
      assistantsData.getAssistants(userData.user?.id || "anonymous");
    }
  }, []);

  // Very hacky way of ensuring updateState is not called when a thread is switched
  useEffect(() => {
    if (threadSwitched) {
      const timer = setTimeout(() => {
        setThreadSwitched(false);
      }, 1000);

      return () => clearTimeout(timer);
    }
  }, [threadSwitched]);

  useEffect(() => {
    return () => {
      debouncedAPIUpdate.cancel();
    };
  }, [debouncedAPIUpdate]);

  useEffect(() => {
    if (!threadData.threadId) return;
    if (!artifact) return;
    if (updateRenderedArtifactRequired || threadSwitched || isStreaming) return;
    const currentIndex = artifact.currentIndex;
    const currentContent = artifact.contents.find(
      (c) => c.index === currentIndex
    );
    if (!currentContent) return;

    // Compare only the current content to avoid expensive full artifact comparison
    // This is much more efficient than comparing the entire artifact
    // Note: currentContent is already defined above, so we reuse it

    // Get the corresponding content from last saved artifact
    const lastSavedContent = lastSavedArtifact.current?.contents.find(
      (c) => c.index === currentIndex
    );

    // Compare only the relevant content fields based on type
    let hasChanged = false;
    if (!lastSavedArtifact.current || !lastSavedContent) {
      hasChanged = true;
    } else if (currentContent.type === "text" && isArtifactMarkdownContent(currentContent)) {
      const lastMarkdown = isArtifactMarkdownContent(lastSavedContent)
        ? lastSavedContent.fullMarkdown
        : null;
      hasChanged = currentContent.fullMarkdown !== lastMarkdown;
    } else {
      // Fallback to JSON comparison for other cases
      hasChanged = JSON.stringify(currentContent) !== JSON.stringify(lastSavedContent);
    }

    // Also check if artifact structure changed (e.g., new content added, index changed)
    if (!hasChanged && lastSavedArtifact.current) {
      hasChanged =
        artifact.currentIndex !== lastSavedArtifact.current.currentIndex ||
        artifact.contents.length !== lastSavedArtifact.current.contents.length;
    }

    if (hasChanged) {
      setIsArtifactSaved(false);
      // This means the artifact in state does not match the last saved artifact
      // We need to update
      debouncedAPIUpdate(artifact, threadData.threadId);
    }
  }, [artifact, threadData.threadId]);

  const searchOrCreateEffectRan = useRef(false);

  // Attempt to load the thread if an ID is present in query params.
  useEffect(() => {
    // Authentication disabled - allow without user
    if (
      typeof window === "undefined" ||
      threadData.createThreadLoading ||
      !threadData.threadId
    ) {
      return;
    }

    // Only run effect once in development
    if (searchOrCreateEffectRan.current) {
      return;
    }
    searchOrCreateEffectRan.current = true;

    // Show loading state when loading from URL
    setIsLoadingThread(true);
    
    threadData.getThread(threadData.threadId).then((thread) => {
      if (thread) {
        switchSelectedThread(thread);
        return;
      }

      // Failed to fetch thread. Remove from query params
      console.warn("Failed to fetch thread from URL:", threadData.threadId);
      toast({
        title: "Thread not found",
        description: "The requested thread could not be found. Starting a new conversation.",
        variant: "destructive",
        duration: 5000,
      });
      threadData.setThreadId(null);
      setIsLoadingThread(false);
    }).catch((error) => {
      console.error("Error loading thread from URL:", error);
      toast({
        title: "Error loading thread",
        description: "Failed to load the requested thread. Starting a new conversation.",
        variant: "destructive",
        duration: 5000,
      });
      threadData.setThreadId(null);
      setIsLoadingThread(false);
    });
  }, [threadData.threadId]);

  const updateArtifact = async (
    artifactToUpdate: Artifact,
    threadId: string
  ) => {
    setArtifactUpdateFailed(false);
    if (isStreaming) return;

    try {
      const response = await fetch(`${API_URL}/api/threads/${threadId}/state`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          values: {
            artifact: artifactToUpdate,
          },
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to update thread state: ${response.statusText}`);
      }

      // Get the updated thread to ensure we have the saved artifact
      const updatedThread = await response.json();
      const savedArtifact = updatedThread?.values?.artifact;
      
      // Use the saved artifact from server response, or fallback to what we sent
      const artifactToSave = savedArtifact || artifactToUpdate;
      
      // Create a deep copy to avoid reference issues
      lastSavedArtifact.current = JSON.parse(JSON.stringify(artifactToSave));
      setIsArtifactSaved(true);
    } catch (error) {
      console.error("Failed to save artifact:", error);
      setArtifactUpdateFailed(true);
    }
  };

  const clearState = () => {
    setMessages([]);
    setArtifact(undefined);
    setFirstTokenReceived(true);
  };

  const streamMessage = async (params: GraphInput) => {
    setFirstTokenReceived(false);
    setError(false);
    
    // API doesn't require assistant ID, but we keep it for compatibility
    // if (!assistantsData.selectedAssistant) {
    //   toast({
    //     title: "Error",
    //     description: "No assistant ID found",
    //     variant: "destructive",
    //     duration: 5000,
    //   });
    //   return;
    // }

    // Ensure thread exists before sending message
    let currentThreadId = threadData.threadId;
    if (!currentThreadId) {
      // Create a thread via LangGraph SDK for proper persistence
      try {
        const newThread = await threadData.createThread();
        if (newThread) {
          currentThreadId = newThread.thread_id;
        } else {
          // Fallback to local thread ID if creation fails
          currentThreadId = `thread-${uuidv4()}`;
          threadData.setThreadId(currentThreadId);
        }
      } catch (e) {
        console.error("Failed to create thread, using local ID:", e);
        // Fallback to local thread ID if creation fails
        currentThreadId = `thread-${uuidv4()}`;
        threadData.setThreadId(currentThreadId);
      }
    }

    // Build full message history: existing messages + new messages
    // Since we don't have checkpoint system, we need to manually accumulate messages
    // First, try to get existing messages from thread, fallback to current state
    let existingMessages: any[] = [];
    if (currentThreadId) {
      try {
        const response = await fetch(`${API_URL}/api/threads/${currentThreadId}`, {
          method: "GET",
        });
        if (response.ok) {
          const thread = await response.json();
          const threadValues = thread?.values as Record<string, any> | undefined;
          if (threadValues?.messages && Array.isArray(threadValues.messages)) {
            // Use messages from thread if available
            existingMessages = threadValues.messages;
          } else {
            // Fallback to current state messages - use LangChain format
            existingMessages = messages.map((msg) => serializeLangChainMessage(msg));
          }
        } else {
          // Fallback to current state messages - use LangChain format
          existingMessages = messages.map((msg) => serializeLangChainMessage(msg));
        }
      } catch (e) {
        console.warn("Failed to load thread messages, using current state:", e);
        // Fallback to current state messages - use LangChain format
        existingMessages = messages.map((msg) => serializeLangChainMessage(msg));
      }
    } else {
      // No thread ID, use current state messages - use LangChain format
      existingMessages = messages.map((msg) => serializeLangChainMessage(msg));
    }
    
    // Combine existing messages with new messages
    const newMessages = params.messages || [];
    const fullMessages = [...existingMessages, ...newMessages];

    // IMPORTANT: Save user's new message immediately to prevent loss
    // This ensures the message is persisted even if streaming fails
    if (currentThreadId && newMessages.length > 0) {
      try {
        await fetch(`${API_URL}/api/threads/${currentThreadId}/state`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            values: {
              messages: fullMessages,
            },
          }),
        });
        console.log("User message saved immediately:", newMessages.map((m: any) => m.id));
      } catch (error) {
        console.error("Failed to save user message immediately:", error);
        // Continue anyway - we'll try to save again after streaming
      }
    }

    const messagesInput = {
      // `messages` contains the full, unfiltered list of messages (existing + new)
      messages: fullMessages,
      // `_messages` contains the list of messages which are included
      // in the LLMs context, including summarization messages.
      _messages: fullMessages,
    };

    // TODO: update to properly pass the highlight data back
    // one field for highlighted text, and one for code
    console.log("[GraphContext] streamMessage - selectedBlocks:", {
      selectedBlocks,
      isUndefined: selectedBlocks === undefined,
      isNull: selectedBlocks === null,
      type: typeof selectedBlocks,
      value: selectedBlocks,
      stringified: JSON.stringify(selectedBlocks),
    });
    
    const input = {
      ...DEFAULT_INPUTS,
      artifact,
      ...params,
      ...messagesInput,
      ...(selectedBlocks && {
        highlightedText: selectedBlocks,
      }),
      webSearchEnabled: searchEnabled,
    };

    console.log("[GraphContext] streamMessage - input.highlightedText:", {
      highlightedText: input.highlightedText,
      isUndefined: input.highlightedText === undefined,
      isNull: input.highlightedText === null,
      type: typeof input.highlightedText,
      value: input.highlightedText,
      stringified: JSON.stringify(input.highlightedText),
    });
    // Add check for multiple defined fields
    const fieldsToCheck = [
      input.highlightedText,
      input.language,
      input.artifactLength,
      input.regenerateWithEmojis,
      input.readingLevel,
      input.customQuickActionId,
    ];

    if (fieldsToCheck.filter((field) => field !== undefined).length >= 2) {
      toast({
        title: "Error",
        description:
          "Can not use multiple fields (quick actions, highlights, etc.) at once. Please try again.",
        variant: "destructive",
        duration: 5000,
      });
      return;
    }

    setIsStreaming(true);
    setRunId(undefined);
    setFeedbackSubmitted(false);
    setFirstTokenReceived(true); // API returns complete response, so we can set this immediately

    try {
      // Stream from API
      // Ensure modelName and modelConfig are set, use defaults if not available
      const modelName = threadData.modelName || DEFAULT_MODEL_NAME;
      // Use the computed modelConfig from ThreadProvider, which handles fallbacks
      const modelConfig = threadData.modelConfig || DEFAULT_MODEL_CONFIG;
      
      // Debug logging
      if (!threadData.modelName) {
        console.warn("Model name not set in threadData, using default:", DEFAULT_MODEL_NAME);
      }
      if (!threadData.modelConfig) {
        console.warn("Model config not set in threadData, using default:", DEFAULT_MODEL_CONFIG);
      }
      
      const config = {
        configurable: {
          customModelName: modelName,
          modelConfig: modelConfig,
          userId: userData.user?.id || "anonymous",
          open_canvas_assistant_id: assistantsData.selectedAssistant?.assistant_id,
          thread_id: currentThreadId,
        },
      };


      const stream = streamAgent(input, config);

      // Variables to keep track of content specific to this stream
      const prevCurrentContent = artifact
        ? artifact.contents.find((a) => a.index === artifact.currentIndex)
        : undefined;

      // The new index of the artifact that is generating
      let newArtifactIndex = 1;
      if (artifact) {
        newArtifactIndex = artifact.contents.length + 1;
      }

      // The metadata generated when re-writing an artifact
      let rewriteArtifactMeta: RewriteArtifactMetaToolResponse | undefined =
        undefined;

      // For generating an artifact
      let generateArtifactToolCallStr = "";

      // For updating code artifacts
      let updatedArtifactStartContent: string | undefined = undefined;
      let updatedArtifactRestContent: string | undefined = undefined;
      let isFirstUpdate = true;

      // The full text content of an artifact that is being rewritten.
      let fullNewArtifactContent = "";
      let newArtifactContent = "";

      // The updated full markdown text when using the highlight update tool
      let highlightedText: TextHighlight | undefined = undefined;

      // The ID of the message for the web search operation during this turn
      let webSearchMessageId = "";

      // The root level run ID of this stream
      let runId = "";
      let followupMessageId = "";
      let thinkingMessageId = "";

      let eventCount = 0;
      // Track node progress content for intermediate results
      const nodeProgressContent: Record<string, string> = {};
      
      // Track messages during streaming to save them later
      // IMPORTANT: Use fullMessages (which includes new user messages) instead of stale `messages` state
      // Convert fullMessages to BaseMessage objects for tracking
      const initialMessages: BaseMessage[] = fullMessages.map((msg: any) => {
        const role = msg.role || "user";
        const content = typeof msg.content === "string" ? msg.content : String(msg.content);
        const id = msg.id || `msg-${Date.now()}-${Math.random()}`;
        
        if (role === "user" || role === "human") {
          return new HumanMessage({
            content,
            id,
            additional_kwargs: msg.additional_kwargs || {},
          });
        } else {
          return new AIMessage({
            content,
            id,
            additional_kwargs: msg.additional_kwargs || {},
            response_metadata: msg.response_metadata || {},
          });
        }
      });
      
      let finalMessages: BaseMessage[] = [...initialMessages];
      let finalArtifact: Artifact | undefined = artifact;
      
      for await (const event of stream) {
        eventCount++;
        const eventType = event?.event || "unknown";
        const nodeName = event?.name || "unknown";
        const langgraphNode = event?.metadata?.langgraph_node || nodeName;
        
        // Log ALL events for debugging
        // console.log(`[EVENT] type: ${eventType}, node: ${langgraphNode}, name: ${nodeName}`);
        
        // API streams LangGraph events in the same format as LangGraph SDK
        // Process events similar to the original streaming logic
        if (event.event === "error") {
          const errorMessage =
            event?.data?.message || "Unknown error. Please try again.";
          toast({
            title: "Error generating content",
            description: errorMessage,
            variant: "destructive",
            duration: 5000,
          });
          setError(true);
          setIsStreaming(false);
          break;
        }

        try {
          const {
            runId: runId_,
            event: eventType,
            name: modelName,
            data,
            tags,
            metadata,
          } = event;
          
          // Get the actual LangGraph node name from metadata
          // LangGraph stores the node name in metadata.langgraph_node
          const langgraphNode = metadata?.langgraph_node || modelName;
          
          if (!runId && runId_) {
            runId = runId_;
            setRunId(runId);
            
            // Update existing "temp" node progress messages with actual runId
            setMessages((prev) => {
              const updated = prev.map((m) => {
                if (m.id?.startsWith("node-progress-") && m.id.includes("-temp")) {
                  // Replace "-temp" with actual runId
                  const newId = m.id.replace("-temp", `-${runId}`);
                  return new AIMessage({
                    ...m,
                    id: newId,
                  });
                }
                return m;
              });
              finalMessages = updated;
              return updated;
            });
          }

          // Process different event types
          if (eventType === "on_chain_start") {
            if (langgraphNode === "updateHighlightedText") {
              highlightedText = data?.input?.highlightedText;
            }

            if (langgraphNode === "queryGenerator" && !webSearchMessageId) {
              webSearchMessageId = `web-search-results-${uuidv4()}`;
              setMessages((prev) => {
                const updated = [
                  ...prev,
                  new AIMessage({
                    id: webSearchMessageId,
                    content: "",
                    additional_kwargs: {
                      [OC_WEB_SEARCH_RESULTS_MESSAGE_KEY]: true,
                      webSearchResults: [],
                      webSearchStatus: "searching",
                    },
                  }),
                ];
                finalMessages = updated;
                return updated;
              });
              setWebSearchResultsId(webSearchMessageId);
            }
          }

          if (eventType === "on_chat_model_stream") {
            const chunk = data?.chunk;
            if (!chunk) {
              console.warn("on_chat_model_stream event has no chunk", { data, langgraphNode });
              continue;
            }
            
            // Extract content from chunk
            const message = extractStreamDataChunk(chunk);
            const content = message?.content || "";
                        
            // Skip empty chunks (Bedrock sends many empty chunks)
            if (!content || content.length === 0) {
              continue;
            }

            // Handle intermediate node progress for nodes that stream content
            // Show progress for all nodes except the final open_canvas graph node
            if (langgraphNode !== "open_canvas" && content) {
              // Accumulate content for this node
              if (!nodeProgressContent[langgraphNode]) {
                nodeProgressContent[langgraphNode] = "";
              }
              nodeProgressContent[langgraphNode] += content;

              // Create or update progress message
              // Use actual runId if available, otherwise use "temp" (will be updated when runId is set)
              const nodeProgressMessageId = `node-progress-${langgraphNode}-${runId || "temp"}`;
              const accumulatedContent = nodeProgressContent[langgraphNode];
              
              if (accumulatedContent.trim().length > 0) {
                const formattedContent = `**${langgraphNode}**\n\n${accumulatedContent}`;
                
                setMessages((prev) => {
                  // Find message by exact ID match first
                  let existingProgressMessage = prev.find(
                    (m) => m.id === nodeProgressMessageId
                  );
                  
                  // If not found and we don't have runId yet, look for "temp" version
                  // But only if it's from this run (check additional_kwargs for nodeProgress flag)
                  if (!existingProgressMessage && !runId) {
                    existingProgressMessage = prev.find(
                      (m) => m.id === `node-progress-${langgraphNode}-temp` &&
                             m.additional_kwargs?.nodeProgress === true &&
                             m.additional_kwargs?.nodeName === langgraphNode
                    );
                  }
                  
                  // If we have runId but message has "temp", look for temp version to update
                  if (!existingProgressMessage && runId) {
                    existingProgressMessage = prev.find(
                      (m) => m.id === `node-progress-${langgraphNode}-temp` &&
                             m.additional_kwargs?.nodeProgress === true &&
                             m.additional_kwargs?.nodeName === langgraphNode
                    );
                  }
                  
                  if (existingProgressMessage) {
                    // Update existing message - also update ID if runId was just set
                    const updated = prev.map((m) => {
                      if (m.id && m.id === existingProgressMessage.id) {
                        // If runId is now available and message has "temp", update the ID
                        const shouldUpdateId = runId && m.id.includes("-temp");
                        const newId = shouldUpdateId 
                          ? `node-progress-${langgraphNode}-${runId}`
                          : m.id;
                        
                        return new AIMessage({
                          ...m,
                          id: newId,
                          content: formattedContent,
                        });
                      }
                      return m;
                    });
                    finalMessages = updated;
                    return updated;
                  } else {
                    // Add new message - this is a new node that hasn't been seen before in this run
                    const updated = [
                      ...prev,
                      new AIMessage({
                        id: nodeProgressMessageId,
                        content: formattedContent,
                        additional_kwargs: {
                          nodeProgress: true,
                          nodeName: langgraphNode,
                          ...(runId && { runId }),
                        },
                      }),
                    ];
                    finalMessages = updated;
                    return updated;
                  }
                });
              }
            }
           
            // These are generating new messages to insert to the chat window.
            if (
              ["generateFollowup", "replyToGeneralInput"].includes(
                langgraphNode
              )
            ) {
              if (!message?.id) {
                message.id = `msg-${Date.now()}-${Math.random()}`;
              }
              
              if (!followupMessageId) {
                followupMessageId = message.id;
              }
              
              setMessages((prevMessages) => {
                const updated = replaceOrInsertMessageChunk(prevMessages, message);
                finalMessages = updated;
                return updated;
              });
            }

            if (langgraphNode === "generateArtifact") {
              // Accumulate content (content is already extracted above)
              generateArtifactToolCallStr += content;

              // For streaming, create artifact directly from accumulated content in real-time
              // Backend generates text directly, not as tool calls
              // Update artifact immediately as content streams in
              if (generateArtifactToolCallStr.length > 0) {
                const artifactContent = generateArtifactToolCallStr;
                
                if (!firstTokenReceived) {
                  setFirstTokenReceived(true);
                }
                
                // Update artifact state immediately for streaming rendering
                // Use functional update to ensure we're working with latest state
                setArtifact((prevArtifact) => {
                  // Create a completely new object to ensure React detects the change
                  const newArtifact = {
                    currentIndex: 1,
                    contents: [
                      {
                        index: 1,
                        type: "text" as const,
                        title: "Generated Artifact",
                        fullMarkdown: artifactContent,
                      },
                    ],
                  };
                  finalArtifact = newArtifact;
                  return newArtifact;
                });
                // Trigger rendering update for each chunk
                setUpdateRenderedArtifactRequired(true);
              }

              // Also try tool call parsing for compatibility (but don't wait for it)
              const result = handleGenerateArtifactToolCallChunk(
                generateArtifactToolCallStr
              );

              if (result && typeof result === "object") {
                if (!firstTokenReceived) {
                  setFirstTokenReceived(true);
                }
                setArtifact(result);
                finalArtifact = result;
                setUpdateRenderedArtifactRequired(true);
              }
            }

            // Handle other node types (updateHighlightedText, updateArtifact, etc.)
            // Similar to original logic but adapted for API event format
            if (langgraphNode === "updateHighlightedText") {
              const message = extractStreamDataChunk(chunk);
              if (!message || !artifact || !highlightedText || !prevCurrentContent) {
                continue;
              }
              if (!isArtifactMarkdownContent(prevCurrentContent)) {
                continue;
              }

              const partialUpdatedContent = message.content || "";
              const startIndexOfHighlightedText =
                highlightedText.fullMarkdown.indexOf(
                  highlightedText.markdownBlock
                );

              if (
                updatedArtifactStartContent === undefined &&
                updatedArtifactRestContent === undefined
              ) {
                updatedArtifactStartContent =
                  highlightedText.fullMarkdown.slice(
                    0,
                    startIndexOfHighlightedText
                  );
                updatedArtifactRestContent = highlightedText.fullMarkdown.slice(
                  startIndexOfHighlightedText +
                    highlightedText.markdownBlock.length
                );
              }

              if (
                updatedArtifactStartContent !== undefined &&
                updatedArtifactRestContent !== undefined
              ) {
                updatedArtifactStartContent += partialUpdatedContent;
              }

              const firstUpdateCopy = isFirstUpdate;
              setFirstTokenReceived(true);
              setArtifact((prev) => {
                if (!prev) {
                  throw new Error("No artifact found when updating markdown");
                }
                const updated = updateHighlightedMarkdown(
                  prev,
                  `${updatedArtifactStartContent}${updatedArtifactRestContent}`,
                  newArtifactIndex,
                  prevCurrentContent,
                  firstUpdateCopy
                );
                finalArtifact = updated;
                return updated;
              });
              // Trigger rendering update for streaming
              setUpdateRenderedArtifactRequired(true);

              if (isFirstUpdate) {
                isFirstUpdate = false;
              }
            }


            // Handle rewrite artifact events
            if (
              [
                "rewriteArtifact",
                "rewriteArtifactTheme",
                "customAction",
              ].includes(langgraphNode)
            ) {
              if (!artifact || !prevCurrentContent || !isArtifactMarkdownContent(prevCurrentContent)) {
                continue;
              }

              fullNewArtifactContent +=
                extractStreamDataChunk(chunk)?.content || "";

              if (isThinkingModel(threadData.modelName)) {
                if (!thinkingMessageId) {
                  thinkingMessageId = `thinking-${uuidv4()}`;
                }
                newArtifactContent = handleRewriteArtifactThinkingModel({
                  newArtifactContent: fullNewArtifactContent,
                  setMessages,
                  thinkingMessageId,
                });
              } else {
                newArtifactContent = fullNewArtifactContent;
              }

              // Use dynamically determined meta if available, otherwise fallback to defaults
              let artifactLanguage: ProgrammingLanguageOptions;
              let artifactType: ArtifactType;
              let artifactTitle: string;

              if (rewriteArtifactMeta) {
                // Use meta from backend (dynamically determined)
                artifactType = rewriteArtifactMeta.type;
                artifactTitle = rewriteArtifactMeta.title || prevCurrentContent.title;
                artifactLanguage = rewriteArtifactMeta.language;
              } else {
                // Fallback to node-based determination
                artifactLanguage = "other";
                artifactType = "text";
                artifactTitle = prevCurrentContent.title;
              }

              const firstUpdateCopy = isFirstUpdate;
              setFirstTokenReceived(true);
                            
              setArtifact((prev) => {
                if (!prev) {
                  throw new Error("No artifact found when updating markdown");
                }

                let content = newArtifactContent;

                const updated = updateRewrittenArtifact({
                  prevArtifact: prev ?? artifact,
                  newArtifactContent: content,
                  rewriteArtifactMeta: {
                    type: artifactType,
                    title: artifactTitle,
                    language: artifactLanguage,
                  },
                  prevCurrentContent: prevCurrentContent,
                  newArtifactIndex,
                  isFirstUpdate: firstUpdateCopy,
                  artifactLanguage,
                });
                
                finalArtifact = updated;
                return updated;
              });
              // Trigger rendering update for streaming
              setUpdateRenderedArtifactRequired(true);

              if (isFirstUpdate) {
                isFirstUpdate = false;
              }
            }
          }

          if (eventType === "on_chain_end") {
            // Log messages from on_chain_end event
            if (data?.output) {
              const output = data.output;
              
              // Log messages if present
              if (output.messages && Array.isArray(output.messages)) {
                console.log(`[on_chain_end] ${langgraphNode} - Messages:`, output.messages);
              }
              
              // Log output data for debugging
              console.log(`[on_chain_end] ${langgraphNode} - Output:`, output);
            }

            // Handle intermediate node results for UI display
            // Show all nodes (except the final open_canvas graph node)
            // Display node name even if there's no output
            if (langgraphNode !== "open_canvas") {
              const output = data?.output || {};
              
              // Check if output has content that should be displayed
              let contentToDisplay: string | null = null;
              
              // Check for messages with content
              if (output.messages && Array.isArray(output.messages) && output.messages.length > 0) {
                const lastMessage = output.messages[output.messages.length - 1];
                if (lastMessage) {
                  let msgContent: string | null = null;
                  
                  if (typeof lastMessage === "string") {
                    const contentMatch = lastMessage.match(/content=['"](.*?)['"]/);
                    msgContent = contentMatch ? contentMatch[1] : null;
                  } else if (lastMessage && typeof lastMessage === "object") {
                    msgContent = typeof lastMessage.content === "string" 
                      ? lastMessage.content 
                      : String(lastMessage.content || "");
                  }
                  
                  // Only show content if it's meaningful (not empty, not just metadata)
                  if (msgContent && msgContent.trim().length > 0 && msgContent.trim().length < 5000) {
                    contentToDisplay = msgContent.trim();
                  }
                }
              }
              
              // Also check for direct content in output
              if (!contentToDisplay && output.content) {
                const outputContent = typeof output.content === "string" 
                  ? output.content 
                  : String(output.content || "");
                if (outputContent.trim().length > 0 && outputContent.trim().length < 5000) {
                  contentToDisplay = outputContent.trim();
                }
              }
              
              // Check for other possible content fields
              if (!contentToDisplay) {
                // Try to find any string content in the output
                for (const [key, value] of Object.entries(output)) {
                  if (key !== "messages" && key !== "artifact" && typeof value === "string" && value.trim().length > 0 && value.trim().length < 5000) {
                    contentToDisplay = value.trim();
                    break;
                  }
                }
              }
              
              // Always show node name, even if there's no content
              // Use actual runId if available, otherwise use "temp" (will be updated when runId is set)
              const nodeProgressMessageId = `node-progress-${langgraphNode}-${runId || "temp"}`;
              const nodeDescription = langgraphNode;
              
              // Create formatted content: node name + content (if available)
              const formattedContent = contentToDisplay && contentToDisplay.trim().length > 0
                ? `**${nodeDescription}**\n\n${contentToDisplay}`
                : `**${nodeDescription}**`;
              
              setMessages((prev) => {
                // Find message by exact ID match first
                let existingProgressMessage = prev.find(
                  (m) => m.id === nodeProgressMessageId
                );
                
                // If not found and we don't have runId yet, look for "temp" version
                // But only if it's from this run (check additional_kwargs for nodeProgress flag)
                if (!existingProgressMessage && !runId) {
                  existingProgressMessage = prev.find(
                    (m) => m.id === `node-progress-${langgraphNode}-temp` &&
                           m.additional_kwargs?.nodeProgress === true &&
                           m.additional_kwargs?.nodeName === langgraphNode
                  );
                }
                
                // If we have runId but message has "temp", look for temp version to update
                if (!existingProgressMessage && runId) {
                  existingProgressMessage = prev.find(
                    (m) => m.id === `node-progress-${langgraphNode}-temp` &&
                           m.additional_kwargs?.nodeProgress === true &&
                           m.additional_kwargs?.nodeName === langgraphNode
                  );
                }
                
                if (existingProgressMessage) {
                  // Update existing message - also update ID if runId was just set
                  const updated = prev.map((m) => {
                    if (m.id && m.id === existingProgressMessage.id) {
                      // If runId is now available and message has "temp", update the ID
                      const shouldUpdateId = runId && m.id.includes("-temp");
                      const newId = shouldUpdateId 
                        ? `node-progress-${langgraphNode}-${runId}`
                        : m.id;
                      
                      return new AIMessage({
                        ...m,
                        id: newId,
                        content: formattedContent,
                      });
                    }
                    return m;
                  });
                  finalMessages = updated;
                  return updated;
                } else {
                  // Add new message - this is a new node that hasn't been seen before in this run
                  const updated = [
                    ...prev,
                    new AIMessage({
                      id: nodeProgressMessageId,
                      content: formattedContent,
                      additional_kwargs: {
                        nodeProgress: true,
                        nodeName: langgraphNode,
                        ...(runId && { runId }),
                      },
                    }),
                  ];
                  finalMessages = updated;
                  return updated;
                }
              });
            }
            
            // Handle final output from open_canvas graph
            if (langgraphNode === "open_canvas" && data?.output) {
              const output = data.output;
              
              // Handle title from generateTitle node (if present in output)
              if (output.title && threadData.threadId) {
                // Update thread metadata with the generated title
                try {
                  const response = await fetch(
                    `${API_URL}/api/threads/${threadData.threadId}/state`,
                    {
                      method: "POST",
                      headers: {
                        "Content-Type": "application/json",
                      },
                      body: JSON.stringify({
                        metadata: {
                          thread_title: output.title,
                        },
                      }),
                    }
                  );

                  if (!response.ok) {
                    const errorText = await response.text();
                    console.error(
                      `Failed to update thread title: ${response.status} ${errorText}`
                    );
                  }
                } catch (error) {
                  console.error("Failed to update thread title:", error);
                }
              }
              
              // Parse artifact if present
              if (output.artifact) {
                const artifactToSet = output.artifact as Artifact;
                
                // Ensure artifact has currentIndex and each content has index and type
                if (!artifactToSet.currentIndex) {
                  artifactToSet.currentIndex = 1;
                }
                if (artifactToSet.contents && Array.isArray(artifactToSet.contents)) {
                  artifactToSet.contents = artifactToSet.contents.map((content, idx) => {
                    // Always use text type
                    const contentType: "text" = "text";
                    
                    // Ensure content has required fields based on type
                    // Use dynamically determined values from backend if available
                    const prevContent = artifact
                      ? artifact.contents.find((c) => c.index === (content.index || idx + 1) - 1)
                      : undefined;
                    
                    // Use title from output.title (from generateTitle) if available and current title is "Untitled"
                    const currentTitle = content.title || prevContent?.title;
                    const shouldUseGeneratedTitle = 
                      output.title && 
                      (!currentTitle || currentTitle === "Untitled" || currentTitle === "Generated Artifact");
                    
                    return {
                      ...content,
                      index: content.index || idx + 1,
                      type: "text" as const,
                      // Use generated title if available, otherwise use content title or "Untitled"
                      title: shouldUseGeneratedTitle 
                        ? output.title 
                        : (currentTitle || "Untitled"),
                      fullMarkdown: ("fullMarkdown" in content ? content.fullMarkdown : "") || "",
                    };
                  });
                }
                
                // Create deep copy to ensure React detects the change
                const artifactCopy = JSON.parse(JSON.stringify(artifactToSet));
                setArtifact(artifactCopy);
                finalArtifact = artifactCopy;
                // Trigger artifact rendering update
                setUpdateRenderedArtifactRequired(true);
                if (!firstTokenReceived) {
                  setFirstTokenReceived(true);
                }
              } else {
                console.log(`[FINAL] No artifact in open_canvas output`);
              }
              
              // Parse messages if present
              // Only add NEW AI messages to chat (user messages are already in UI via optimistic update)
              // Artifact generation messages should only appear in the canvas via the artifact
              if (output.messages && Array.isArray(output.messages)) {
                
                const parsedMessages: BaseMessage[] = [];
                const artifactMessageIds = new Set<string>();
                
                // Get user message IDs that were just sent (these are already in UI)
                const justSentUserMessageIds = new Set(
                  newMessages.map((msg: any) => msg.id).filter(Boolean)
                );
                
                // First pass: identify which messages are from generateArtifact
                // generateArtifact messages are the ones that match the artifact content
                // and are NOT from generateFollowup
                if (output.artifact && output.artifact.contents && output.artifact.contents.length > 0) {
                  const artifactContent = output.artifact.contents[0];
                  const artifactText = artifactContent.fullMarkdown || "";
                  
                  for (let i = 0; i < output.messages.length; i++) {
                    const msg = output.messages[i];
                    let msgId: string | null = null;
                    let msgContent: string | null = null;
                    
                    if (typeof msg === "string") {
                      const idMatch = msg.match(/id=['"](.*?)['"]/);
                      const contentMatch = msg.match(/content=['"](.*?)['"]/);
                      msgId = idMatch ? idMatch[1] : null;
                      msgContent = contentMatch ? contentMatch[1] : null;
                    } else if (msg && typeof msg === "object") {
                      msgId = msg.id || null;
                      msgContent = typeof msg.content === "string" ? msg.content : String(msg.content || "");
                    }
                    
                    // If this message's content matches the artifact content, it's from generateArtifact
                    // generateArtifact messages have the same content as the artifact
                    // generateFollowup messages have different, shorter content
                    if (msgId && msgContent) {
                      const msgContentTrimmed = msgContent.trim();
                      // Check if content matches artifact (first 200 chars for comparison)
                      const compareLength = Math.min(200, artifactText.length, msgContentTrimmed.length);
                      const msgContentStart = msgContentTrimmed.substring(0, compareLength).trim();
                      const artifactContentStart = artifactText.substring(0, compareLength).trim();
                      
                      // If content matches artifact exactly (or starts with artifact), it's from generateArtifact
                      // generateFollowup messages are shorter and have different content
                      if (msgContentStart === artifactContentStart && msgContentTrimmed.length > 50) {
                        artifactMessageIds.add(msgId);
                      }
                    }
                  }
                }
                
                // Second pass: parse and add messages, skipping artifact generation messages
                for (const msg of output.messages) {
                  // Skip invalid messages early
                  if (!msg || (typeof msg !== "string" && typeof msg !== "object")) {
                    continue;
                  }
                  
                  let messageObj: BaseMessage;
                  
                  // If message is a string (legacy format), try to parse it
                  if (typeof msg === "string") {
                    // Parse string like: "content='하이' additional_kwargs={'documents': []} response_metadata={} id='fb873f8b-2c62-49c9-8518-d6f579b9ab18'"
                    const contentMatch = msg.match(/content=['"](.*?)['"]/);
                    const idMatch = msg.match(/id=['"](.*?)['"]/);
                    const additionalKwargsMatch = msg.match(/additional_kwargs=({.*?})/);
                    
                    const content = contentMatch ? contentMatch[1] : "";
                    const id = idMatch ? idMatch[1] : uuidv4();
                    
                    // Skip messages that are from generateArtifact node
                    if (artifactMessageIds.has(id)) {
                      console.log("Skipping generateArtifact message (canvas only):", id);
                      continue;
                    }
                    
                    // Try to parse additional_kwargs (convert Python dict to JSON)
                    let additionalKwargs = {};
                    if (additionalKwargsMatch) {
                      try {
                        // Replace Python dict syntax with JSON
                        const kwargsStr = additionalKwargsMatch[1]
                          .replace(/'/g, '"')
                          .replace(/True/g, 'true')
                          .replace(/False/g, 'false')
                          .replace(/None/g, 'null');
                        additionalKwargs = JSON.parse(kwargsStr);
                      } catch (e) {
                        console.warn("Failed to parse additional_kwargs:", e);
                      }
                    }
                    
                    // Determine message type from string representation
                    let messageType = "ai";
                    if (msg.includes("HumanMessage")) {
                      messageType = "human";
                    } else if (msg.includes("AIMessage") || msg.includes("lc_run--")) {
                      messageType = "ai";
                    }
                    
                    if (messageType === "human") {
                      messageObj = new HumanMessage({
                        content,
                        id,
                        additional_kwargs: additionalKwargs,
                      });
                    } else {
                      messageObj = new AIMessage({
                        content,
                        id,
                        additional_kwargs: additionalKwargs,
                      });
                    }
                  } else if (msg && typeof msg === "object" && msg.content !== undefined) {
                    // Message is a dict (new format from backend)
                    const content = typeof msg.content === "string" ? msg.content : String(msg.content);
                    const id = msg.id || uuidv4();
                    const additionalKwargs = msg.additional_kwargs || {};
                    const responseMetadata = msg.response_metadata || {};
                    
                    // Determine message type: prioritize backend's type field, then use heuristics
                    let msgType = msg.type || "ai";
                    
                    // If backend sent type, trust it (after our fix, it should be correct)
                    // But also apply heuristics as fallback for backwards compatibility
                    if (msg.type === "human" || msg.type === "user") {
                      msgType = "human";
                    } else if (msg.type === "ai" || msg.type === "assistant") {
                      msgType = "ai";
                    } else {
                      // Fallback heuristics if type is missing or unknown
                      // Rule 1: If it has documents in additional_kwargs, it's a user message
                      if (additionalKwargs.documents && Array.isArray(additionalKwargs.documents)) {
                        msgType = "human";
                      }
                      // Rule 2: If it doesn't have lc_run-- in ID, check other characteristics
                      if (!id.includes("lc_run--")) {
                        // User messages typically don't have response_metadata with model info
                        const hasModelMetadata = responseMetadata.model_name || responseMetadata.model_provider;
                        if (!hasModelMetadata) {
                          msgType = "human";
                        }
                      }
                    // Rule 3: If it's the first message and doesn't have lc_run--, it's likely user input
                    const isFirstMessage = output.messages.indexOf(msg) === 0;
                    if (isFirstMessage && !id.includes("lc_run--")) {
                      // First message without lc_run-- is almost certainly user input
                      msgType = "human";
                    }
                      // Rule 4: If response_metadata is empty or minimal, it's likely a user message
                      if (Object.keys(responseMetadata).length === 0 && !id.includes("lc_run--")) {
                        msgType = "human";
                      }
                    }
                    
                    // Skip messages that are from generateArtifact node
                    if (artifactMessageIds.has(id)) {
                      console.log("Skipping generateArtifact message (canvas only):", id);
                      continue;
                    }
                    
                    // Also check if content matches artifact (for messages without lc_run-- in ID)
                    // This is important because artifact generation messages should not appear in chat
                    if (output.artifact && output.artifact.contents && output.artifact.contents.length > 0) {
                      // Check all artifact contents, not just the first one
                      for (const artifactContent of output.artifact.contents) {
                        const artifactText = artifactContent.fullMarkdown || "";
                        if (artifactText && content.trim().length > 50) {
                          // More lenient comparison - check if content is similar to artifact
                          const compareLength = Math.min(300, artifactText.length, content.trim().length);
                          const contentStart = content.trim().substring(0, compareLength).trim();
                          const artifactStart = artifactText.substring(0, compareLength).trim();
                          
                          // If content matches artifact (or is very similar), skip it
                          // This catches cases where artifact content appears as a message
                          if (contentStart === artifactStart || 
                              (contentStart.length > 100 && 
                               artifactStart.length > 100 &&
                               contentStart.substring(0, 100) === artifactStart.substring(0, 100))) {
                            console.log("Skipping message with artifact content (canvas only):", id);
                            continue;
                          }
                          
                          // Also check if message content is a substring of artifact (artifact is longer)
                          if (artifactText.length > content.trim().length * 0.8 && 
                              artifactText.includes(content.trim().substring(0, Math.min(200, content.trim().length)))) {
                            console.log("Skipping message that matches artifact substring (canvas only):", id);
                            continue;
                          }
                        }
                      }
                    }
                    
                    if (msgType === "human" || msgType === "user") {
                      messageObj = new HumanMessage({
                        content,
                        id,
                        additional_kwargs: additionalKwargs,
                        response_metadata: responseMetadata,
                      });
                    } else {
                      messageObj = new AIMessage({
                        content,
                        id,
                        additional_kwargs: additionalKwargs,
                        response_metadata: responseMetadata,
                      });
                    }
                  } else {
                    continue; // Skip invalid messages
                  }
                  
                  // Validate message before adding to parsedMessages
                  if (!messageObj || !messageObj.id || messageObj.content === undefined || messageObj.content === null) {
                    console.warn("Skipping invalid message:", messageObj);
                    continue;
                  }
                  
                  parsedMessages.push(messageObj);
                }
                
                if (parsedMessages.length > 0) {
                  setMessages((prev) => {
                    // Simple deduplication by ID
                    const existingIds = new Set(prev.map(m => m.id));
                    
                    // Filter out duplicates and messages already in UI
                    const newMessages = parsedMessages.filter(m => {
                      // Skip if already exists (by ID)
                      if (existingIds.has(m.id)) {
                        return false;
                      }
                      
                      // OPTIMISTIC UI: Skip user messages that were just sent
                      // These are already in the UI from the optimistic update
                      if (m instanceof HumanMessage && justSentUserMessageIds.has(m.id)) {
                        console.log("Skipping user message (already in UI from optimistic update):", m.id);
                        return false;
                      }
                      
                      // Final safety check: if message content matches artifact, skip it
                      if (finalArtifact && finalArtifact.contents && finalArtifact.contents.length > 0) {
                        const msgContent = typeof m.content === "string" ? m.content : String(m.content || "");
                        for (const artifactContent of finalArtifact.contents) {
                          const artifactText = isArtifactMarkdownContent(artifactContent) 
                            ? artifactContent.fullMarkdown 
                            : "";
                          if (artifactText && msgContent.trim().length > 50) {
                            const compareLength = Math.min(200, artifactText.length, msgContent.trim().length);
                            const msgStart = msgContent.trim().substring(0, compareLength).trim();
                            const artifactStart = artifactText.substring(0, compareLength).trim();
                            if (msgStart === artifactStart) {
                              console.log("Final filter: Skipping message with artifact content:", m.id);
                              return false;
                            }
                          }
                        }
                      }
                      
                      return true;
                    });
                    const updated = [...prev, ...newMessages];
                    finalMessages = updated;
                    return updated;
                  });
                }
              }
            }
            
            if (
              langgraphNode === "rewriteArtifact" &&
              data?.output
            ) {
              // Extract meta information from rewriteArtifact output
              // The output may contain artifact meta (type, title, language)
              const output = data.output;
              
              // Check if output has artifact with meta information
              if (output.artifact?.contents && output.artifact.contents.length > 0) {
                const latestContent = output.artifact.contents[output.artifact.contents.length - 1];
                if (latestContent) {
                  rewriteArtifactMeta = {
                    type: "text" as ArtifactType,
                    title: latestContent.title || prevCurrentContent?.title || "Untitled",
                    language: "other" as ProgrammingLanguageOptions,
                  };
                }
              } else if (output.type || output.title || output.language) {
                // Direct meta in output
                rewriteArtifactMeta = {
                  type: "text" as ArtifactType,
                  title: output.title || prevCurrentContent?.title || "Untitled",
                  language: "other" as ProgrammingLanguageOptions,
                };
              }
            }

            if (langgraphNode === "search" && webSearchMessageId) {
              const output = data?.output as {
                webSearchResults: SearchResult[];
              };

              if (output?.webSearchResults) {
                setMessages((prev) => {
                  const updated = prev.map((m) => {
                    if (m.id !== webSearchMessageId) return m;

                    return new AIMessage({
                      ...m,
                      additional_kwargs: {
                        ...m.additional_kwargs,
                        webSearchResults: output.webSearchResults,
                        webSearchStatus: "done",
                      },
                    });
                  });
                  finalMessages = updated;
                  return updated;
                });
              }
            }

            // Handle generateTitle node output - save as thread title
            if (langgraphNode === "generateTitle" && data?.output) {
              const output = data.output as { title?: string };
              const title = output?.title;
              
              if (title && threadData.threadId) {
                // Update thread metadata with the generated title
                try {
                  const response = await fetch(
                    `${API_URL}/api/threads/${threadData.threadId}/state`,
                    {
                      method: "POST",
                      headers: {
                        "Content-Type": "application/json",
                      },
                      body: JSON.stringify({
                        metadata: {
                          thread_title: title,
                        },
                      }),
                    }
                  );

                  if (!response.ok) {
                    const errorText = await response.text();
                    console.error(
                      `Failed to update thread title: ${response.status} ${errorText}`
                    );
                  } else {
                    // Optionally update artifact title if it's "Untitled"
                    if (artifact && artifact.contents && artifact.contents.length > 0) {
                      const currentTitle = artifact.contents[0]?.title;
                      if (!currentTitle || currentTitle === "Untitled" || currentTitle === "Generated Artifact") {
                        setArtifact((prev) => {
                          if (!prev) return prev;
                          return {
                            ...prev,
                            contents: prev.contents.map((content, idx) => 
                              idx === 0 ? { ...content, title } : content
                            ),
                          };
                        });
                      }
                    }
                  }
                } catch (error) {
                  console.error("Failed to update thread title:", error);
                }
              }
            }

            if (
              langgraphNode === "generateArtifact" &&
              !generateArtifactToolCallStr &&
              NON_STREAMING_TOOL_CALLING_MODELS.some(
                (m) => m === threadData.modelName
              )
            ) {
              const message = data?.output;
              generateArtifactToolCallStr +=
                message?.tool_call_chunks?.[0]?.args || message?.content || "";
              const result = handleGenerateArtifactToolCallChunk(
                generateArtifactToolCallStr
              );
              if (result && result === "continue") {
                continue;
              } else if (result && typeof result === "object") {
                setFirstTokenReceived(true);
                setArtifact(result);
                finalArtifact = result;
              }
            }
          }
        } catch (e: any) {
          console.error("Failed to parse stream event", event, "\n\nError:\n", e);

          let errorMessage = "Unknown error. Please try again.";
          if (typeof e === "object" && e?.message) {
            errorMessage = e.message;
          }

          toast({
            title: "Error generating content",
            description: errorMessage,
            variant: "destructive",
            duration: 5000,
          });
          setError(true);
          setIsStreaming(false);
          break;
        }
      }

      // Use the tracked final values instead of state (which might be stale)
      const messagesToSave = finalMessages.length > 0 ? finalMessages : messages;
      const artifactToSave = finalArtifact || artifact;
      
      lastSavedArtifact.current = artifactToSave;
      
      // Save messages and artifact to thread after streaming completes
      // This matches the original implementation structure
      if (currentThreadId && messagesToSave.length > 0) {
        try {
          // Filter out node-progress messages - these are UI-only and shouldn't be saved
          const messagesToSerialize = messagesToSave.filter(
            (msg) => !msg.id?.startsWith("node-progress-")
          );
          
          // Convert messages to serializable format - use LangChain format (type field)
          const serializedMessages = messagesToSerialize.map((msg) => {
            try {
              const serialized = serializeLangChainMessage(msg);
              // Remove large document data from additional_kwargs before saving
              // Documents are already converted to context messages, so we only need metadata
              if (serialized.additional_kwargs?.documents && Array.isArray(serialized.additional_kwargs.documents)) {
                serialized.additional_kwargs = {
                  ...serialized.additional_kwargs,
                  documents: serialized.additional_kwargs.documents.map((doc: any) => ({
                    name: doc.name,
                    type: doc.type,
                    // Don't include the large 'data' field to avoid storage issues
                  })),
                };
              }
              return serialized;
            } catch (serializeError) {
              console.error("Failed to serialize message:", msg, serializeError);
              // Return a safe fallback instead of breaking the entire save
              return {
                type: "ai",
                content: typeof msg.content === "string" ? msg.content : String(msg.content || ""),
                id: msg.id || `msg-${Date.now()}-${Math.random()}`,
                additional_kwargs: {},
              };
            }
          });
          
          const requestBody = {
            values: {
              messages: serializedMessages,
              ...(artifactToSave && { artifact: artifactToSave }),
            },
          };
          
          const response = await fetch(`${API_URL}/api/threads/${currentThreadId}/state`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(requestBody),
          });

          if (!response.ok) {
            const errorText = await response.text();
            console.error(`Failed to update thread state: ${response.status} ${response.statusText}`, errorText.substring(0, 200));
            throw new Error(`Failed to update thread state: ${response.status} ${response.statusText}`);
          }
        } catch (saveError) {
          console.error("Failed to save messages and artifact to thread:", saveError);
          // Don't show error to user as this is a background operation
        }
      }
    } catch (e: any) {
      console.error("Failed to call API", e);
      const errorMessage =
        e?.message || "Unknown error. Please try again.";
      toast({
        title: "Error generating content",
        description: errorMessage,
        variant: "destructive",
        duration: 5000,
      });
      setError(true);
    } finally {
      setSelectedBlocks(undefined);
      setIsStreaming(false);
    }
  };

  const setSelectedArtifact = async (index: number) => {
    setUpdateRenderedArtifactRequired(true);
    // Don't set threadSwitched here - it prevents artifact updates

    const currentThreadId = threadData.threadId;
    if (!currentThreadId) {
      toast({
        title: "Error",
        description: "No thread selected",
        variant: "destructive",
        duration: 5000,
      });
      return;
    }

    setArtifact((prev) => {
      if (!prev) {
        toast({
          title: "Error",
          description: "No artifact found",
          variant: "destructive",
          duration: 5000,
        });
        return prev;
      }

      // Check if we already have this version loaded
      const hasVersion = prev.contents?.some((c: any) => c.index === index);
      if (hasVersion) {
        // Version already loaded, just update currentIndex
        const newArtifact = {
          ...prev,
          currentIndex: index,
        };
        lastSavedArtifact.current = newArtifact;
        return newArtifact;
      }

      // Need to fetch this version from server
      // Set loading state first
      return prev;
    });

    // Fetch the specific version from server
    try {
      const response = await fetch(
        `${API_URL}/api/threads/${currentThreadId}/artifact/versions/${index}`
      );
      if (!response.ok) {
        if (response.status === 404) {
          // Version doesn't exist, check if it's in metadata
          setArtifact((prev) => {
            if (!prev) return prev;
            const metadata = (prev as any)._metadata;
            if (metadata && metadata.version_indices) {
              const validIndices = metadata.version_indices;
              if (!validIndices.includes(index)) {
                toast({
                  title: "Error",
                  description: `Artifact version ${index} does not exist. Available versions: ${validIndices.join(", ")}`,
                  variant: "destructive",
                  duration: 5000,
                });
              }
            }
            return prev;
          });
        } else {
          throw new Error(`Failed to fetch artifact version ${index}: ${response.statusText}`);
        }
        return;
      }

      const versionArtifact = await response.json();
      
      setArtifact((prev) => {
        if (!prev) {
          return prev;
        }

        // Merge the new version into existing artifact
        const existingContents = prev.contents || [];
        const newContent = versionArtifact.contents?.[0];
        
        if (newContent) {
          // Check if this version already exists
          const existingIndex = existingContents.findIndex((c: any) => c.index === index);
          let updatedContents;
          
          if (existingIndex >= 0) {
            // Replace existing version
            updatedContents = [...existingContents];
            updatedContents[existingIndex] = newContent;
          } else {
            // Add new version
            updatedContents = [...existingContents, newContent];
          }

          const newArtifact = {
            ...prev,
            currentIndex: index,
            contents: updatedContents,
          };
          lastSavedArtifact.current = newArtifact;
          return newArtifact;
        }

        return prev;
      });
    } catch (error) {
      console.error("Failed to fetch artifact version:", error);
      toast({
        title: "Error",
        description: `Failed to load artifact version ${index}`,
        variant: "destructive",
        duration: 5000,
      });
    }
  };

  const setArtifactContent = (index: number, content: string) => {
    setArtifact((prev) => {
      if (!prev) {
        toast({
          title: "Error",
          description: "No artifact found",
          variant: "destructive",
          duration: 5000,
        });
        return prev;
      }
      const newArtifact = {
        ...prev,
        currentIndex: index,
        contents: prev.contents.map((a) => {
          if (a.index === index && a.type === "code") {
            return {
              ...a,
              code: reverseCleanContent(content),
            };
          }
          return a;
        }),
      };
      return newArtifact;
    });
  };

  const refreshArtifactMetadata = async () => {
    const currentThreadId = threadData.threadId;
    if (!currentThreadId || !artifact) return;

    try {
      // Fetch version metadata
      const metadataResponse = await fetch(
        `${API_URL}/api/threads/${currentThreadId}/artifact/versions`
      );
      if (metadataResponse.ok) {
        const metadata = await metadataResponse.json();
        
        // Get the latest version index from metadata
        const latestIndex = metadata.current_index;
        const currentIndex = artifact.currentIndex;
        
        // Update artifact with new metadata
        setArtifact((prev) => {
          if (!prev) return prev;
          
          // Update metadata
          return {
            ...prev,
            _metadata: metadata,
          } as Artifact & { _metadata?: any };
        });
        
        // If we have a newer version, load it
        if (latestIndex && latestIndex !== currentIndex) {
          await setSelectedArtifact(latestIndex);
        } else if (latestIndex && latestIndex === currentIndex) {
          // Even if index is same, refresh the current version to get latest content
          await setSelectedArtifact(latestIndex);
        }
      }
    } catch (error) {
      console.error("Failed to refresh artifact metadata:", error);
    }
  };

  const switchSelectedThread = async (thread: Thread) => {
    // Start loading
    setIsLoadingThread(true);
    setUpdateRenderedArtifactRequired(true);
    setThreadSwitched(true);
    // Reset diff mode when switching threads to avoid version mismatch issues
    setIsDiffMode(false);
    setDiffBaseVersionIndex(undefined);
    // Don't set chatStarted here - wait until we know if thread has content
    // setChatStarted(true);

    try {
      // Set the thread ID in state. Then set in cookies so a new thread
      // isn't created on page load if one already exists.
      threadData.setThreadId(thread.thread_id);

      // Fetch full thread data including latest artifact version and all messages
      const fullThread = await threadData.getThread(thread.thread_id);
      if (!fullThread) {
        console.error("Failed to fetch full thread data for thread:", thread.thread_id);
        toast({
          title: "Error",
          description: "Failed to load thread. Please try again.",
          variant: "destructive",
          duration: 5000,
        });
        setIsLoadingThread(false);
        return;
      }

    // Set the model name and config
    if (fullThread.metadata?.customModelName) {
      threadData.setModelName(
        fullThread.metadata.customModelName as ALL_MODEL_NAMES
      );
      threadData.setModelConfig(
        fullThread.metadata.customModelName as ALL_MODEL_NAMES,
        fullThread.metadata.modelConfig as CustomModelConfig
      );
    } else {
      threadData.setModelName(DEFAULT_MODEL_NAME);
      threadData.setModelConfig(DEFAULT_MODEL_NAME, DEFAULT_MODEL_CONFIG);
    }

    const castValues: {
      artifact: Artifact | undefined;
      messages: Record<string, any>[] | undefined;
    } = {
      artifact: undefined,
      messages: (fullThread.values as Record<string, any>)?.messages || undefined,
    };
    const castThreadValues = fullThread.values as Record<string, any>;
    if (castThreadValues?.artifact) {
      try {
        const artifact = castThreadValues.artifact as Artifact;
        // The artifact from server now contains only the latest version
        // Ensure currentIndex is set correctly
        if (artifact.contents && artifact.contents.length > 0) {
          const contentIndex = artifact.contents[0]?.index || artifact.currentIndex || 1;
          castValues.artifact = {
            ...artifact,
            currentIndex: contentIndex,
          };
        } else {
          console.warn("Artifact has no contents, using as-is");
          castValues.artifact = artifact;
        }
        
        // Fetch version metadata to know total versions
        try {
          const metadataResponse = await fetch(
            `${API_URL}/api/threads/${thread.thread_id}/artifact/versions`
          );
          if (metadataResponse.ok) {
            const metadata = await metadataResponse.json();
            // Store version metadata in artifact for UI navigation
            if (castValues.artifact) {
              castValues.artifact = {
                ...castValues.artifact,
                // Store metadata for navigation
                _metadata: metadata,
              } as Artifact & { _metadata?: any };
            }
          } else {
            console.warn("Failed to fetch artifact version metadata: HTTP", metadataResponse.status);
          }
        } catch (e) {
          console.warn("Failed to fetch artifact version metadata:", e);
        }
        
        // Update artifact title with thread title if available and artifact title is "Untitled"
        const threadTitle = fullThread.metadata?.thread_title;
        if (threadTitle && castValues.artifact) {
          const currentTitle = castValues.artifact.contents?.[0]?.title;
          if (!currentTitle || currentTitle === "Untitled" || currentTitle === "Generated Artifact") {
            castValues.artifact = {
              ...castValues.artifact,
              contents: castValues.artifact.contents?.map((content: any) => ({
                ...content,
                title: threadTitle,
              })) || [],
            };
          }
        }
      } catch (error) {
        console.error("Failed to parse artifact from thread:", error);
        castValues.artifact = undefined;
      }
    } else {
      castValues.artifact = undefined;
    }
    // Create a deep copy to avoid reference issues
    lastSavedArtifact.current = castValues?.artifact 
      ? JSON.parse(JSON.stringify(castValues.artifact))
      : undefined;
    
    // Mark artifact as saved since we just loaded it from the server
    setIsArtifactSaved(true);

    // Always set artifact first (even if no messages)
    setArtifact(castValues?.artifact);
    
    // If no messages, set empty array and return
    if (!castValues?.messages || castValues.messages.length === 0) {
      console.log("No messages in thread, setting empty message array");
      setMessages([]);
      return;
    }
    
    // Validate that messages is an array
    if (!Array.isArray(castValues.messages)) {
      console.error("Messages is not an array:", typeof castValues.messages, castValues.messages);
      toast({
        title: "Error",
        description: "Thread data is corrupted. Messages are not in the correct format.",
        variant: "destructive",
        duration: 5000,
      });
      setMessages([]);
      return;
    }
        
    // Ensure all messages have valid IDs before setting
    const messagesWithIds = castValues.messages
      .map((msg: Record<string, any>, index: number) => {
        try {
          // Convert plain object to BaseMessage instance
          // Use role field (standard format: user/assistant/system)
          const role = msg.role || "user";
          const content = msg.content || "";
          
          // Ensure ID is ALWAYS a valid string - never allow empty/invalid IDs
          let id = msg.id;
          if (!id || typeof id !== "string" || id.trim().length === 0) {
            // Generate a unique ID if missing or invalid
            id = `msg-${thread.thread_id}-${index}-${uuidv4()}`;
            console.log(`Generated ID for message at index ${index}:`, id);
          } else {
            id = id.trim();
          }
          
          const additional_kwargs = msg.additional_kwargs || {};
          
          let baseMessage: BaseMessage;
          
          if (role === "user" || role === "human") {
            baseMessage = new HumanMessage({
              content,
              id,
              additional_kwargs,
            });
          } else if (role === "assistant" || role === "ai") {
            baseMessage = new AIMessage({
              content,
              id,
              additional_kwargs,
              tool_calls: msg.tool_calls || [],
              response_metadata: msg.response_metadata || {},
            });
          } else if (role === "system") {
            baseMessage = new HumanMessage({  // SystemMessage if available, otherwise HumanMessage
              content,
              id,
              additional_kwargs,
            });
          } else {
            // Default to HumanMessage for unknown roles
            console.warn(`Unknown message role "${role}" at index ${index}, defaulting to HumanMessage`);
            baseMessage = new HumanMessage({
              content,
              id,
              additional_kwargs,
            });
          }
          
          // Handle langSmithRunURL
          if (msg.response_metadata?.langSmithRunURL) {
            const toolCalls = (baseMessage as AIMessage).tool_calls || [];
            toolCalls.push({
              name: "langsmith_tool_ui",
              args: { sharedRunURL: msg.response_metadata.langSmithRunURL },
              id: msg.response_metadata.langSmithRunURL
                ?.split("https://smith.langchain.com/public/")[1]
                .split("/")[0],
            });
            (baseMessage as AIMessage).tool_calls = toolCalls;
          }
          
          return baseMessage;
        } catch (error) {
          console.error(`Failed to parse message at index ${index}:`, error, msg);
          // Return null for failed messages - will be filtered out
          return null;
        }
      })
      .filter((msg: BaseMessage | null): msg is BaseMessage => {
        // Filter out null messages (parsing failures)
        // All valid messages now have guaranteed valid IDs from the map step
        if (msg === null) {
          console.warn("Filtered out null message (parsing failed)");
          return false;
        }
        
        // Double-check ID validity (should always pass now)
        if (!msg.id || typeof msg.id !== "string" || msg.id.trim().length === 0) {
          console.error("Message has invalid ID after mapping - this should not happen:", msg);
          return false;
        }
        
        return true;
      });
    
    console.log(`Loaded ${messagesWithIds.length} messages for thread ${thread.thread_id}`);
    
    // If we had messages but none were successfully parsed, warn the user
    if (castValues.messages.length > 0 && messagesWithIds.length === 0) {
      console.error(`All ${castValues.messages.length} messages failed to parse for thread ${thread.thread_id}`);
      toast({
        title: "Warning",
        description: `Failed to load ${castValues.messages.length} message(s). The thread may be corrupted.`,
        variant: "destructive",
        duration: 7000,
      });
    } else if (messagesWithIds.length < castValues.messages.length) {
      const failedCount = castValues.messages.length - messagesWithIds.length;
      console.warn(`${failedCount} message(s) failed to parse for thread ${thread.thread_id}`);
      toast({
        title: "Warning",
        description: `${failedCount} message(s) could not be loaded. Some conversation history may be missing.`,
        variant: "destructive",
        duration: 5000,
      });
    }
    
    setMessages(messagesWithIds);
    
    // Set chatStarted based on whether thread has content
    // Chat should be "started" if there are messages OR artifact present
    const hasMessages = messagesWithIds.length > 0;
    const hasArtifact = !!castValues.artifact;
    const shouldStartChat = hasMessages || hasArtifact;
    
    console.log(`Thread ${thread.thread_id} - hasMessages: ${hasMessages}, hasArtifact: ${hasArtifact}, setChatStarted: ${shouldStartChat}`);
    setChatStarted(shouldStartChat);
    } catch (error) {
      console.error("Error in switchSelectedThread:", error);
      toast({
        title: "Error",
        description: "An unexpected error occurred while loading the thread.",
        variant: "destructive",
        duration: 5000,
      });
    } finally {
      // Always stop loading, even if there was an error
      setIsLoadingThread(false);
    }
  };

  const contextValue: GraphContentType = {
    graphData: {
      runId,
      isStreaming,
      isLoadingThread,
      error,
      selectedBlocks,
      messages,
      artifact,
      updateRenderedArtifactRequired,
      isArtifactSaved,
      firstTokenReceived,
      feedbackSubmitted,
      chatStarted,
      artifactUpdateFailed,
      searchEnabled,
      isDiffMode,
      diffBaseVersionIndex,
      setSearchEnabled,
      setChatStarted,
      setIsStreaming,
      setFeedbackSubmitted,
      setArtifact,
      setSelectedBlocks,
      setSelectedArtifact,
      setMessages,
      streamMessage,
      setArtifactContent,
      clearState,
      switchSelectedThread,
      setUpdateRenderedArtifactRequired,
      setIsDiffMode,
      setDiffBaseVersionIndex,
      refreshArtifactMetadata,
    },
  };

  return (
    <GraphContext.Provider value={contextValue}>
      {children}
    </GraphContext.Provider>
  );
}

export function useGraphContext() {
  const context = useContext(GraphContext);
  if (context === undefined) {
    throw new Error("useGraphContext must be used within a GraphProvider");
  }
  return context;
}
