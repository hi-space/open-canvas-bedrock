import { v4 as uuidv4 } from "uuid";
import { useUserContext } from "@/contexts/UserContext";
import {
  isArtifactCodeContent,
  isArtifactMarkdownContent,
  isDeprecatedArtifactType,
} from "@/shared/utils/artifacts";
import { reverseCleanContent } from "@/lib/normalize_string";
import {
  ArtifactType,
  ArtifactV3,
  CustomModelConfig,
  GraphInput,
  ProgrammingLanguageOptions,
  RewriteArtifactMetaToolResponse,
  SearchResult,
  TextHighlight,
} from "@/shared/types";
import { AIMessage, BaseMessage } from "@langchain/core/messages";
import { useRuns } from "@/hooks/useRuns";
import { streamFastAPIAgent } from "@/lib/fastapi-client";
import { WEB_SEARCH_RESULTS_QUERY_PARAM } from "@/constants";
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
  convertToArtifactV3,
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
// import { StreamWorkerService } from "@/workers/graph-stream/streamWorker"; // Removed - FastAPI doesn't support streaming
import { useQueryState } from "nuqs";

interface GraphData {
  runId: string | undefined;
  isStreaming: boolean;
  error: boolean;
  selectedBlocks: TextHighlight | undefined;
  messages: BaseMessage[];
  artifact: ArtifactV3 | undefined;
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
  setArtifact: Dispatch<SetStateAction<ArtifactV3 | undefined>>;
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
  if (Array.isArray(chunk)) {
    return chunk[1];
  }
  return chunk;
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
  const [artifact, setArtifact] = useState<ArtifactV3>();
  const [selectedBlocks, setSelectedBlocks] = useState<TextHighlight>();
  const [isStreaming, setIsStreaming] = useState(false);
  const [updateRenderedArtifactRequired, setUpdateRenderedArtifactRequired] =
    useState(false);
  const lastSavedArtifact = useRef<ArtifactV3 | undefined>(undefined);
  const debouncedAPIUpdate = useRef(
    debounce(
      (artifact: ArtifactV3, threadId: string) =>
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
    artifactToUpdate: ArtifactV3,
    threadId: string
  ) => {
    setArtifactUpdateFailed(false);
    if (isStreaming) return;

    try {
      // TODO: Implement artifact update via FastAPI
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

  const streamMessageV2 = async (params: GraphInput) => {
    setFirstTokenReceived(false);
    setError(false);
    
    // FastAPI doesn't require assistant ID, but we keep it for compatibility
    // if (!assistantsData.selectedAssistant) {
    //   toast({
    //     title: "Error",
    //     description: "No assistant ID found",
    //     variant: "destructive",
    //     duration: 5000,
    //   });
    //   return;
    // }

    // FastAPI doesn't use thread management, but we keep threadId for local state
    let currentThreadId = threadData.threadId;
    if (!currentThreadId) {
      // Create a simple thread ID for local tracking
      currentThreadId = `thread-${uuidv4()}`;
      threadData.setThreadId(currentThreadId);
    }

    const messagesInput = {
      // `messages` contains the full, unfiltered list of messages
      messages: params.messages,
      // `_messages` contains the list of messages which are included
      // in the LLMs context, including summarization messages.
      _messages: params.messages,
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
    setFirstTokenReceived(true); // FastAPI returns complete response, so we can set this immediately

    try {
      // Stream from FastAPI
      const config = {
        configurable: {
          customModelName: threadData.modelName,
          modelConfig: threadData.modelConfigs[threadData.modelName],
        },
      };

      const stream = streamFastAPIAgent(input, config);

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

      for await (const event of stream) {
        // FastAPI streams LangGraph events in the same format as LangGraph SDK
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
            name: langgraphNode,
            data,
          } = event;

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
                return [
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
              });
              setWebSearchResultsId(webSearchMessageId);
            }
          }

          if (eventType === "on_chat_model_stream") {
            const chunk = data?.chunk;
            if (!chunk) continue;

            // These are generating new messages to insert to the chat window.
            if (
              ["generateFollowup", "replyToGeneralInput"].includes(
                langgraphNode
              )
            ) {
              const message = extractStreamDataChunk(chunk);
              if (!followupMessageId) {
                followupMessageId = message.id;
              }
              setMessages((prevMessages) =>
                replaceOrInsertMessageChunk(prevMessages, message)
              );
            }

            if (langgraphNode === "generateArtifact") {
              const message = extractStreamDataChunk(chunk);

              // Accumulate content
              if (
                message?.tool_call_chunks?.length > 0 &&
                typeof message?.tool_call_chunks?.[0]?.args === "string"
              ) {
                generateArtifactToolCallStr += message.tool_call_chunks[0].args;
              } else if (
                message?.content &&
                typeof message?.content === "string"
              ) {
                generateArtifactToolCallStr += message.content;
              }

              // Process accumulated content with rate limiting
              const result = handleGenerateArtifactToolCallChunk(
                generateArtifactToolCallStr
              );

              if (result) {
                if (result === "continue") {
                  continue;
                } else if (typeof result === "object") {
                  if (!firstTokenReceived) {
                    setFirstTokenReceived(true);
                  }
                  setArtifact(result);
                }
              }
            }

            // Handle other node types (updateHighlightedText, updateArtifact, etc.)
            // Similar to original logic but adapted for FastAPI event format
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
                return updateHighlightedMarkdown(
                  prev,
                  `${updatedArtifactStartContent}${updatedArtifactRestContent}`,
                  newArtifactIndex,
                  prevCurrentContent,
                  firstUpdateCopy
                );
              });

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
                return updateHighlightedCode(
                  prev,
                  content,
                  newArtifactIndex,
                  prevCurrentContent,
                  firstUpdateCopy
                );
              });

              if (isFirstUpdate) {
                isFirstUpdate = false;
              }
            }

            // Handle rewrite artifact events
            if (
              [
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

              const artifactLanguage =
                params.portLanguage ||
                (isArtifactCodeContent(prevCurrentContent)
                  ? prevCurrentContent.language
                  : "other");

              let artifactType: ArtifactType;
              if (langgraphNode === "rewriteCodeArtifactTheme") {
                artifactType = "code";
              } else if (langgraphNode === "rewriteArtifactTheme") {
                artifactType = "text";
              } else {
                artifactType = prevCurrentContent.type;
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

                return updateRewrittenArtifact({
                  prevArtifact: prev ?? artifact,
                  newArtifactContent: content,
                  rewriteArtifactMeta: {
                    type: artifactType,
                    title: prevCurrentContent.title,
                    language: artifactLanguage,
                  },
                  prevCurrentContent,
                  newArtifactIndex,
                  isFirstUpdate: firstUpdateCopy,
                  artifactLanguage,
                });
              });

              if (isFirstUpdate) {
                isFirstUpdate = false;
              }
            }
          }

          if (eventType === "on_chain_end") {
            if (
              langgraphNode === "rewriteArtifact" &&
              data?.output
            ) {
              rewriteArtifactMeta = data.output;
            }

            if (langgraphNode === "search" && webSearchMessageId) {
              const output = data?.output as {
                webSearchResults: SearchResult[];
              };

              if (output?.webSearchResults) {
                setMessages((prev) => {
                  return prev.map((m) => {
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

      lastSavedArtifact.current = artifact;
    } catch (e: any) {
      console.error("Failed to call FastAPI", e);
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
      artifact: ArtifactV3 | undefined;
      messages: Record<string, any>[] | undefined;
    } = {
      artifact: undefined,
      messages: (thread.values as Record<string, any>)?.messages || undefined,
    };
    const castThreadValues = thread.values as Record<string, any>;
    if (castThreadValues?.artifact) {
      if (isDeprecatedArtifactType(castThreadValues.artifact)) {
        castValues.artifact = convertToArtifactV3(castThreadValues.artifact);
      } else {
        castValues.artifact = castThreadValues.artifact;
      }
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
      streamMessage: streamMessageV2,
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
