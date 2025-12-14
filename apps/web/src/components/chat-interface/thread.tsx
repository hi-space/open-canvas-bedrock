import { useGraphContext } from "@/contexts/GraphContext";
import { useToast } from "@/hooks/use-toast";
import { ProgrammingLanguageOptions } from "@/shared/types";
import { ThreadPrimitive, useExternalStoreRuntime, useExternalMessageConverter, AssistantRuntimeProvider } from "@assistant-ui/react";
import { Thread as ThreadType } from "@langchain/langgraph-sdk";
import { ArrowDownIcon, PanelRightOpen, SquarePen } from "lucide-react";
import { Dispatch, FC, SetStateAction, useMemo } from "react";
import { ReflectionsDialog } from "../reflections-dialog/ReflectionsDialog";
import { useLangSmithLinkToolUI } from "../tool-hooks/LangSmithLinkToolUI";
import { TooltipIconButton } from "../ui/assistant-ui/tooltip-icon-button";
import { TighterText } from "../ui/header";
import { Composer } from "./composer";
import { AssistantMessage, UserMessage } from "./messages";
import ModelSelector from "./model-selector";
import { ThreadHistory } from "./thread-history";
import { ThreadWelcome } from "./welcome";
import { useUserContext } from "@/contexts/UserContext";
import { useAssistantContext } from "@/contexts/AssistantContext";
import { Checkbox } from "../ui/checkbox";
import { Label } from "../ui/label";
import useLocalStorage from "@/hooks/useLocalStorage";
import { BaseMessage, HumanMessage } from "@langchain/core/messages";
import { convertLangchainMessages, serializeLangChainMessage } from "@/lib/convert_messages";
import { CompositeAttachmentAdapter, SimpleTextAttachmentAdapter, AppendMessage } from "@assistant-ui/react";
import { AudioAttachmentAdapter } from "../ui/assistant-ui/attachment-adapters/audio";
import { VideoAttachmentAdapter } from "../ui/assistant-ui/attachment-adapters/video";
import { PDFAttachmentAdapter } from "../ui/assistant-ui/attachment-adapters/pdf";
import { ImageAttachmentAdapter } from "../ui/assistant-ui/attachment-adapters/image";
import { v4 as uuidv4 } from "uuid";
import { useThreadContext } from "@/contexts/ThreadProvider";

const ThreadScrollToBottom: FC = () => {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <TooltipIconButton
        tooltip="Scroll to bottom"
        variant="outline"
        className="absolute -top-8 rounded-full disabled:invisible"
      >
        <ArrowDownIcon />
      </TooltipIconButton>
    </ThreadPrimitive.ScrollToBottom>
  );
};

export interface ThreadProps {
  userId: string | undefined;
  hasChatStarted: boolean;
  handleQuickStart: (
    type: "text" | "code",
    language?: ProgrammingLanguageOptions
  ) => void;
  setChatStarted: Dispatch<SetStateAction<boolean>>;
  switchSelectedThreadCallback: (thread: ThreadType) => void;
  searchEnabled: boolean;
  setChatCollapsed: (c: boolean) => void;
}

export const Thread: FC<ThreadProps> = (props: ThreadProps) => {
  const {
    hasChatStarted,
    handleQuickStart,
    switchSelectedThreadCallback,
  } = props;
  const { toast } = useToast();
  const {
    graphData: { clearState, runId, feedbackSubmitted, setFeedbackSubmitted, isLoadingThread, messages, isStreaming, streamMessage, setMessages, setIsStreaming, setChatStarted: setChatStartedFromContext },
  } = useGraphContext();
  const { selectedAssistant } = useAssistantContext();
  const {
    modelName,
    setModelName,
    modelConfig,
    setModelConfig,
    modelConfigs,
    setThreadId,
  } = useThreadContext();
  const { user } = useUserContext();
  const [expandNodeAccordions, setExpandNodeAccordions] = useLocalStorage<boolean>(
    "expandNodeAccordions",
    false
  );

  // Render the LangSmith trace link
  useLangSmithLinkToolUI();

  const { getUserThreads } = useThreadContext();

  // Handle new messages from Composer
  const onNew = async (message: AppendMessage): Promise<void> => {
    // Explicitly check for false and not ! since this does not provide a default value
    // so we should assume undefined is true.
    if (message.startRun === false) return;

    if (message.content?.[0]?.type !== "text") {
      toast({
        title: "Only text messages are supported",
        variant: "destructive",
        duration: 5000,
      });
      return;
    }

    setChatStartedFromContext(true);
    setIsStreaming(true);

    try {
      const humanMessage = new HumanMessage({
        content: message.content[0].text,
        id: uuidv4(),
        additional_kwargs: {},
      });

      setMessages((prevMessages) => [...prevMessages, humanMessage]);

      await streamMessage({
        messages: [serializeLangChainMessage(humanMessage)],
      });
    } finally {
      setIsStreaming(false);
      // Re-fetch threads so that the current thread's title is updated.
      // Silently fail if getUserThreads fails
      getUserThreads().catch((e) => {
        console.warn("Failed to refresh thread list after message:", e);
      });
    }
  };

  // Filter and validate messages before passing to assistant-ui
  // This prevents "Entry not available in the store" errors
  const validMessages = useMemo(() => {
    return messages.filter((msg): msg is BaseMessage => {
      // Ensure message exists and has a valid ID
      if (!msg) return false;
      if (!msg.id || typeof msg.id !== "string" || msg.id.trim().length === 0) {
        console.warn("Filtering out message without valid ID:", msg);
        return false;
      }
      // Ensure message has content
      if (msg.content === undefined || msg.content === null) {
        console.warn("Filtering out message without content:", msg.id);
        return false;
      }
      return true;
    });
  }, [messages]);

  const threadMessages = useExternalMessageConverter<BaseMessage>({
    callback: convertLangchainMessages,
    messages: validMessages,
    isRunning: isStreaming,
    joinStrategy: "none",
  });

  const runtime = useExternalStoreRuntime({
    messages: threadMessages,
    isRunning: isStreaming,
    onNew,
    adapters: {
      attachments: new CompositeAttachmentAdapter([
        new SimpleTextAttachmentAdapter(),
        new AudioAttachmentAdapter(),
        new VideoAttachmentAdapter(),
        new PDFAttachmentAdapter(),
        new ImageAttachmentAdapter(),
      ]),
    },
  });

  const handleNewSession = async () => {
    // Authentication disabled - allow new session without user
    // Remove the threadId param from the URL
    setThreadId(null);

    setModelName(modelName);
    setModelConfig(modelName, modelConfig);
    clearState();
    setChatStartedFromContext(false);
  };

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex flex-col h-full w-full">
      <div className="pr-3 pl-6 pt-3 pb-2 flex flex-row gap-4 items-center justify-between">
        <div className="flex items-center justify-start gap-2 text-gray-600">
          <ThreadHistory
            switchSelectedThreadCallback={switchSelectedThreadCallback}
          />
          <TighterText className="text-xl">Open Canvas</TighterText>
          {!hasChatStarted && (
            <ModelSelector
              modelName={modelName}
              setModelName={setModelName}
              modelConfig={modelConfig}
              setModelConfig={setModelConfig}
              modelConfigs={modelConfigs}
            />
          )}
        </div>
        {hasChatStarted ? (
          <div className="flex flex-row flex-1 gap-2 items-center justify-end">
            <TooltipIconButton
              tooltip="Collapse Chat"
              variant="ghost"
              className="w-8 h-8"
              delayDuration={400}
              onClick={() => props.setChatCollapsed(true)}
            >
              <PanelRightOpen className="text-gray-600" />
            </TooltipIconButton>
            <TooltipIconButton
              tooltip="New chat"
              variant="ghost"
              className="w-8 h-8"
              delayDuration={400}
              onClick={handleNewSession}
            >
              <SquarePen className="text-gray-600" />
            </TooltipIconButton>
          </div>
        ) : (
          <div className="flex flex-row gap-2 items-center">
            <ReflectionsDialog selectedAssistant={selectedAssistant} />
          </div>
        )}
      </div>
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto scroll-smooth bg-inherit px-4 pt-8">
        {!hasChatStarted && (
          <ThreadWelcome
            handleQuickStart={handleQuickStart}
            composer={
              <Composer
                chatStarted={false}
                userId={props.userId}
                searchEnabled={props.searchEnabled}
              />
            }
            searchEnabled={props.searchEnabled}
          />
        )}
        {isLoadingThread && hasChatStarted && (
          <div className="flex items-center justify-center py-8">
            <div className="flex flex-col items-center gap-3">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-600"></div>
              <p className="text-sm text-gray-500">Loading thread...</p>
            </div>
          </div>
        )}
        {!isLoadingThread && (
          <ThreadPrimitive.Messages
            components={{
              UserMessage: UserMessage,
              AssistantMessage: (prop) => (
                <AssistantMessage
                  {...prop}
                  feedbackSubmitted={feedbackSubmitted}
                  setFeedbackSubmitted={setFeedbackSubmitted}
                  runId={runId}
                />
              ),
            }}
          />
        )}
      </ThreadPrimitive.Viewport>
      <div className="mt-4 flex w-full flex-col items-center justify-end rounded-t-lg bg-inherit pb-4 px-4">
        <ThreadScrollToBottom />
        <div className="w-full max-w-2xl">
          {hasChatStarted && (
            <div className="flex flex-col space-y-2">
              <div className="flex items-center justify-between gap-4">
                <ModelSelector
                  modelName={modelName}
                  setModelName={setModelName}
                  modelConfig={modelConfig}
                  setModelConfig={setModelConfig}
                  modelConfigs={modelConfigs}
                />
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="expand-accordions"
                    checked={expandNodeAccordions}
                    onCheckedChange={(checked) => setExpandNodeAccordions(checked === true)}
                  />
                  <Label
                    htmlFor="expand-accordions"
                    className="text-sm text-gray-600 cursor-pointer"
                  >
                    Detail
                  </Label>
                </div>
              </div>
              <Composer
                chatStarted={true}
                userId={props.userId}
                searchEnabled={props.searchEnabled}
              />
            </div>
          )}
        </div>
      </div>
    </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
};
