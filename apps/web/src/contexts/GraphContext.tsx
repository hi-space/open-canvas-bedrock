import { v4 as uuidv4 } from "uuid";
import { useUserContext } from "@/contexts/UserContext";
import {
  isArtifactCodeContent,
  isArtifactMarkdownContent,
} from "@/shared/utils/artifacts";
import { reverseCleanContent } from "@/lib/normalize_string";
import {
  Artifact,
  ArtifactType,
  CustomModelConfig,
  GraphInput,
  ProgrammingLanguageOptions,
  RewriteArtifactMetaToolResponse,
  SearchResult,
  TextHighlight,
} from "@/shared/types";
import { AIMessage, BaseMessage, HumanMessage } from "@langchain/core/messages";
import { useRuns } from "@/hooks/useRuns";
import { streamAgent } from "@/lib/api-client";
import { WEB_SEARCH_RESULTS_QUERY_PARAM } from "@/constants";
import { createClient } from "@/hooks/utils";
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
  updateHighlightedCode,
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
// import { StreamWorkerService } from "@/workers/graph-stream/streamWorker"; // Removed - streaming not supported
import { useQueryState } from "nuqs";

interface GraphData {
  runId: string | undefined;
  isStreaming: boolean;
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
  switchSelectedThread: (thread: Thread) => void;
  setUpdateRenderedArtifactRequired: Dispatch<SetStateAction<boolean>>;
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
      5000
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

  const [_, setWebSearchResultsId] = useQueryState(
    WEB_SEARCH_RESULTS_QUERY_PARAM
  );

  useEffect(() => {
    // Authentication disabled - allow without user
    if (typeof window === "undefined") return;

    // Get or create a new assistant if there isn't one set in state, and we're not
    // loading all assistants already.
    if (
      !assistantsData.selectedAssistant &&
      !assistantsData.isLoadingAllAssistants
    ) {
      assistantsData.getOrCreateAssistant(userData.user?.id || "anonymous");
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
    if (!messages.length || !artifact) return;
    if (updateRenderedArtifactRequired || threadSwitched || isStreaming) return;
    const currentIndex = artifact.currentIndex;
    const currentContent = artifact.contents.find(
      (c) => c.index === currentIndex
    );
    if (!currentContent) return;
    if (
      (artifact.contents.length === 1 &&
        artifact.contents[0].type === "text" &&
        !artifact.contents[0].fullMarkdown) ||
      (artifact.contents[0].type === "code" && !artifact.contents[0].code)
    ) {
      // If the artifact has only one content and it's empty, we shouldn't update the state
      return;
    }

    if (
      !lastSavedArtifact.current ||
      lastSavedArtifact.current.contents !== artifact.contents
    ) {
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

    threadData.getThread(threadData.threadId).then((thread) => {
      if (thread) {
        switchSelectedThread(thread);
        return;
      }

      // Failed to fetch thread. Remove from query params
      threadData.setThreadId(null);
    });
  }, [threadData.threadId]);

  const updateArtifact = async (
    artifactToUpdate: Artifact,
    threadId: string
  ) => {
    setArtifactUpdateFailed(false);
    if (isStreaming) return;

    try {
      // TODO: Implement artifact update via API
      // For now, just update local state
      setIsArtifactSaved(true);
      lastSavedArtifact.current = artifactToUpdate;
    } catch (_) {
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
        const client = createClient();
        const thread = await client.threads.get(currentThreadId);
        const threadValues = thread?.values as Record<string, any> | undefined;
        if (threadValues?.messages && Array.isArray(threadValues.messages)) {
          // Use messages from thread if available
          existingMessages = threadValues.messages;
        } else {
          // Fallback to current state messages
          existingMessages = messages.map((msg) => {
            const msgType = msg.constructor.name === "HumanMessage" ? "user" :
                            msg.constructor.name === "AIMessage" ? "assistant" : "system";
            return {
              role: msgType,
              content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content),
              id: msg.id,
              ...((msg as any).additional_kwargs && { additional_kwargs: (msg as any).additional_kwargs }),
            };
          });
        }
      } catch (e) {
        console.warn("Failed to load thread messages, using current state:", e);
        // Fallback to current state messages
        existingMessages = messages.map((msg) => {
          const msgType = msg.constructor.name === "HumanMessage" ? "user" :
                          msg.constructor.name === "AIMessage" ? "assistant" : "system";
          return {
            role: msgType,
            content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content),
            id: msg.id,
            ...((msg as any).additional_kwargs && { additional_kwargs: (msg as any).additional_kwargs }),
          };
        });
      }
    } else {
      // No thread ID, use current state messages
      existingMessages = messages.map((msg) => {
        const msgType = msg.constructor.name === "HumanMessage" ? "user" :
                        msg.constructor.name === "AIMessage" ? "assistant" : "system";
        return {
          role: msgType,
          content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content),
          id: msg.id,
          ...((msg as any).additional_kwargs && { additional_kwargs: (msg as any).additional_kwargs }),
        };
      });
    }
    
    // Combine existing messages with new messages
    const newMessages = params.messages || [];
    const fullMessages = [...existingMessages, ...newMessages];

    const messagesInput = {
      // `messages` contains the full, unfiltered list of messages (existing + new)
      messages: fullMessages,
      // `_messages` contains the list of messages which are included
      // in the LLMs context, including summarization messages.
      _messages: fullMessages,
    };

    // TODO: update to properly pass the highlight data back
    // one field for highlighted text, and one for code
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
    // Add check for multiple defined fields
    const fieldsToCheck = [
      input.highlightedCode,
      input.highlightedText,
      input.language,
      input.artifactLength,
      input.regenerateWithEmojis,
      input.readingLevel,
      input.addComments,
      input.addLogs,
      input.fixBugs,
      input.portLanguage,
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
      // Track messages during streaming to save them later
      let finalMessages: BaseMessage[] = [...messages];
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

            if (langgraphNode === "updateArtifact") {
              if (!artifact || !params.highlightedCode || !prevCurrentContent) {
                continue;
              }
              if (prevCurrentContent.type !== "code") {
                continue;
              }

              const partialUpdatedContent =
                extractStreamDataChunk(chunk)?.content || "";
              const { startCharIndex, endCharIndex } = params.highlightedCode;

              if (
                updatedArtifactStartContent === undefined &&
                updatedArtifactRestContent === undefined
              ) {
                updatedArtifactStartContent = prevCurrentContent.code.slice(
                  0,
                  startCharIndex
                );
                updatedArtifactRestContent =
                  prevCurrentContent.code.slice(endCharIndex);
              } else {
                updatedArtifactStartContent += partialUpdatedContent;
              }

              const firstUpdateCopy = isFirstUpdate;
              setFirstTokenReceived(true);
              setArtifact((prev) => {
                if (!prev) {
                  throw new Error("No artifact found when updating markdown");
                }
                const content = removeCodeBlockFormatting(
                  `${updatedArtifactStartContent}${updatedArtifactRestContent}`
                );
                const updated = updateHighlightedCode(
                  prev,
                  content,
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
                "rewriteCodeArtifactTheme",
                "customAction",
              ].includes(langgraphNode)
            ) {
              if (!artifact || !prevCurrentContent) {
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
                artifactLanguage =
                  params.portLanguage ||
                  (isArtifactCodeContent(prevCurrentContent)
                    ? prevCurrentContent.language
                    : "other");

                if (langgraphNode === "rewriteCodeArtifactTheme") {
                  artifactType = "code";
                } else if (langgraphNode === "rewriteArtifactTheme") {
                  artifactType = "text";
                } else {
                  artifactType = prevCurrentContent.type;
                }
                artifactTitle = prevCurrentContent.title;
              }

              const firstUpdateCopy = isFirstUpdate;
              setFirstTokenReceived(true);
                            
              setArtifact((prev) => {
                if (!prev) {
                  throw new Error("No artifact found when updating markdown");
                }

                let content = newArtifactContent;
                if (artifactType === "code") {
                  content = removeCodeBlockFormatting(content);
                }

                const updated = updateRewrittenArtifact({
                  prevArtifact: prev ?? artifact,
                  newArtifactContent: content,
                  rewriteArtifactMeta: {
                    type: artifactType,
                    title: artifactTitle,
                    language: artifactLanguage,
                  },
                  prevCurrentContent,
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
            
            // Handle final output from open_canvas graph
            if (langgraphNode === "open_canvas" && data?.output) {
              const output = data.output;
              
              // Parse artifact if present
              if (output.artifact) {
                const artifactToSet = output.artifact as Artifact;
                
                // Ensure artifact has currentIndex and each content has index and type
                if (!artifactToSet.currentIndex) {
                  artifactToSet.currentIndex = 1;
                }
                if (artifactToSet.contents && Array.isArray(artifactToSet.contents)) {
                  artifactToSet.contents = artifactToSet.contents.map((content, idx) => {
                    // Determine type from content structure
                    let contentType: "text" | "code" = content.type as "text" | "code";
                    if (!contentType) {
                      // Infer type from content structure
                      if ("fullMarkdown" in content && content.fullMarkdown !== undefined) {
                        contentType = "text";
                      } else if ("code" in content && content.code !== undefined) {
                        contentType = "code";
                      } else {
                        // Default to text if cannot determine
                        contentType = "text";
                      }
                    }
                    
                    // Ensure content has required fields based on type
                    // Use dynamically determined values from backend if available
                    const prevContent = artifact
                      ? artifact.contents.find((c) => c.index === (content.index || idx + 1) - 1)
                      : undefined;
                    
                    if (contentType === "text") {
                      return {
                        ...content,
                        index: content.index || idx + 1,
                        type: "text" as const,
                        // Use title from content if available (may be dynamically determined)
                        title: content.title || prevContent?.title || "Generated Artifact",
                        fullMarkdown: ("fullMarkdown" in content ? content.fullMarkdown : "") || "",
                      };
                    } else {
                      return {
                        ...content,
                        index: content.index || idx + 1,
                        type: "code" as const,
                        // Use title from content if available (may be dynamically determined)
                        title: content.title || prevContent?.title || "Generated Artifact",
                        // Use language from content if available (may be dynamically determined)
                        language: ("language" in content ? content.language : 
                          (prevContent && isArtifactCodeContent(prevContent)
                            ? prevContent.language 
                            : "typescript")) as any,
                        code: ("code" in content ? content.code : "") || "",
                      };
                    }
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
                
                console.log(`[FINAL] Artifact set from open_canvas on_chain_end: ${artifactCopy.contents[artifactCopy.contents.length - 1].fullMarkdown}`);
              } else {
                console.log(`[FINAL] No artifact in open_canvas output`);
              }
              
              // Parse messages if present
              // Only add followup messages to chat, not artifact generation messages
              // Artifact generation messages should only appear in the canvas via the artifact
              if (output.messages && Array.isArray(output.messages)) {
                
                const parsedMessages: BaseMessage[] = [];
                const artifactMessageIds = new Set<string>();
                
                // First pass: identify which messages are from generateArtifact
                // generateArtifact messages are the ones that match the artifact content
                // and are NOT from generateFollowup
                if (output.artifact && output.artifact.contents && output.artifact.contents.length > 0) {
                  const artifactContent = output.artifact.contents[0];
                  const artifactText = artifactContent.fullMarkdown || artifactContent.code || "";
                  
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
                        const artifactText = artifactContent.fullMarkdown || artifactContent.code || "";
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
                  
                  parsedMessages.push(messageObj);
                }
                
                if (parsedMessages.length > 0) {
                  setMessages((prev) => {
                    // Filter out messages that are already in the list (by ID)
                    const existingIds = new Set(prev.map(m => m.id));
                    // Also filter out user messages - they're already in the chat
                    // And filter out any messages that match artifact content
                    const newMessages = parsedMessages.filter(m => {
                      // Skip if already exists
                      if (existingIds.has(m.id)) {
                        return false;
                      }
                      // Skip user messages - they're already in the chat from when user sent them
                      if (m instanceof HumanMessage) {
                        return false;
                      }
                      
                      // Final safety check: if message content matches artifact, skip it
                      if (finalArtifact && finalArtifact.contents && finalArtifact.contents.length > 0) {
                        const msgContent = typeof m.content === "string" ? m.content : String(m.content || "");
                        for (const artifactContent of finalArtifact.contents) {
                          const artifactText = isArtifactMarkdownContent(artifactContent) 
                            ? artifactContent.fullMarkdown 
                            : isArtifactCodeContent(artifactContent)
                            ? artifactContent.code
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
                    type: latestContent.type as ArtifactType,
                    title: latestContent.title || prevCurrentContent?.title || "Untitled",
                    language: (latestContent.language || 
                      (isArtifactCodeContent(prevCurrentContent) 
                        ? prevCurrentContent.language 
                        : "other")) as ProgrammingLanguageOptions,
                  };
                }
              } else if (output.type || output.title || output.language) {
                // Direct meta in output
                rewriteArtifactMeta = {
                  type: (output.type || prevCurrentContent?.type || "text") as ArtifactType,
                  title: output.title || prevCurrentContent?.title || "Untitled",
                  language: (output.language || 
                    (isArtifactCodeContent(prevCurrentContent) 
                      ? prevCurrentContent.language 
                      : "other")) as ProgrammingLanguageOptions,
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
          const client = createClient();
          // Convert messages to serializable format
          const serializedMessages = messagesToSave.map((msg) => {
            const baseMsg: any = {
              type: msg.constructor.name === "HumanMessage" ? "human" : 
                    msg.constructor.name === "AIMessage" ? "ai" : "system",
              content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content),
              id: msg.id,
            };
            if ((msg as any).additional_kwargs) {
              baseMsg.additional_kwargs = (msg as any).additional_kwargs;
            }
            if ((msg as any).response_metadata) {
              baseMsg.response_metadata = (msg as any).response_metadata;
            }
            if ((msg as any).usage_metadata) {
              baseMsg.usage_metadata = (msg as any).usage_metadata;
            }
            return baseMsg;
          });
          
          await client.threads.updateState(currentThreadId, {
            values: {
              messages: serializedMessages,
              ...(artifactToSave && { artifact: artifactToSave }),
            },
          });
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

  const setSelectedArtifact = (index: number) => {
    setUpdateRenderedArtifactRequired(true);
    setThreadSwitched(true);

    setArtifact((prev) => {
      if (!prev) {
        toast({
          title: "Error",
          description: "No artifactV2 found",
          variant: "destructive",
          duration: 5000,
        });
        return prev;
      }
      const newArtifact = {
        ...prev,
        currentIndex: index,
      };
      lastSavedArtifact.current = newArtifact;
      return newArtifact;
    });
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

  const switchSelectedThread = (thread: Thread) => {
    setUpdateRenderedArtifactRequired(true);
    setThreadSwitched(true);
    setChatStarted(true);

    // Set the thread ID in state. Then set in cookies so a new thread
    // isn't created on page load if one already exists.
    threadData.setThreadId(thread.thread_id);

    // Set the model name and config
    if (thread.metadata?.customModelName) {
      threadData.setModelName(
        thread.metadata.customModelName as ALL_MODEL_NAMES
      );
      threadData.setModelConfig(
        thread.metadata.customModelName as ALL_MODEL_NAMES,
        thread.metadata.modelConfig as CustomModelConfig
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
      messages: (thread.values as Record<string, any>)?.messages || undefined,
    };
    const castThreadValues = thread.values as Record<string, any>;
    if (castThreadValues?.artifact) {
      castValues.artifact = castThreadValues.artifact as Artifact;
    } else {
      castValues.artifact = undefined;
    }
    lastSavedArtifact.current = castValues?.artifact;

    if (!castValues?.messages?.length) {
      setMessages([]);
      setArtifact(castValues?.artifact);
      return;
    }
    setArtifact(castValues?.artifact);
    setMessages(
      castValues.messages.map((msg: Record<string, any>) => {
        if (msg.response_metadata?.langSmithRunURL) {
          msg.tool_calls = msg.tool_calls ?? [];
          msg.tool_calls.push({
            name: "langsmith_tool_ui",
            args: { sharedRunURL: msg.response_metadata.langSmithRunURL },
            id: msg.response_metadata.langSmithRunURL
              ?.split("https://smith.langchain.com/public/")[1]
              .split("/")[0],
          });
        }
        return msg as BaseMessage;
      })
    );
  };

  const contextValue: GraphContentType = {
    graphData: {
      runId,
      isStreaming,
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
