"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  ActionBarPrimitive,
  getExternalStoreMessage,
  MessagePrimitive,
  MessageState,
  useMessage,
} from "@assistant-ui/react";
import React, { Dispatch, SetStateAction, type FC } from "react";

import { MarkdownText } from "@/components/ui/assistant-ui/markdown-text";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { FeedbackButton } from "./feedback";
import { TighterText } from "../ui/header";
import { useFeedback } from "@/hooks/useFeedback";
import { ContextDocumentsUI } from "../tool-hooks/AttachmentsToolUI";
import { HumanMessage } from "@langchain/core/messages";
import { Button } from "../ui/button";
import { WEB_SEARCH_RESULTS_QUERY_PARAM } from "@/constants";
import { Globe } from "lucide-react";
import { useQueryState } from "nuqs";
import { TextHighlight } from "@/shared/types";
import useLocalStorage from "@/hooks/useLocalStorage";

interface AssistantMessageProps {
  runId: string | undefined;
  feedbackSubmitted: boolean;
  setFeedbackSubmitted: Dispatch<SetStateAction<boolean>>;
}

const ThinkingAssistantMessageComponent = ({
  message,
}: {
  message: MessageState;
}): React.ReactElement => {
  const { id, content } = message;
  const [expandNodeAccordions] = useLocalStorage<boolean>(
    "expandNodeAccordions",
    false
  );
  
  let contentText = "";
  if (typeof content === "string") {
    contentText = content;
  } else {
    const firstItem = content?.[0];
    if (firstItem?.type === "text") {
      contentText = firstItem.text;
    }
  }

  if (contentText === "") {
    return <></>;
  }

  return (
    <Accordion
      defaultValue={expandNodeAccordions ? `accordion-${id}` : undefined}
      type="single"
      collapsible
      className="w-full"
    >
      <AccordionItem value={`accordion-${id}`}>
        <AccordionTrigger>Thoughts</AccordionTrigger>
        <AccordionContent>{contentText}</AccordionContent>
      </AccordionItem>
    </Accordion>
  );
};

const ThinkingAssistantMessage = React.memo(ThinkingAssistantMessageComponent);

const WebSearchMessageComponent = ({ message }: { message: MessageState }) => {
  const [_, setShowWebResultsId] = useQueryState(
    WEB_SEARCH_RESULTS_QUERY_PARAM
  );

  const handleShowWebSearchResults = () => {
    if (!message.id) {
      return;
    }

    setShowWebResultsId(message.id);
  };

  return (
    <div className="flex mx-8">
      <Button
        onClick={handleShowWebSearchResults}
        variant="secondary"
        className="bg-blue-50 hover:bg-blue-100 transition-all ease-in-out duration-200 w-full"
      >
        <Globe className="size-4 mr-2" />
        Web Search Results
      </Button>
    </div>
  );
};

const WebSearchMessage = React.memo(WebSearchMessageComponent);

const NodeProgressMessageComponent = ({
  message,
}: {
  message: MessageState;
}): React.ReactElement => {
  const { id, content } = message;
  const [expandNodeAccordions] = useLocalStorage<boolean>(
    "expandNodeAccordions",
    false
  );
  
  let contentText = "";
  if (typeof content === "string") {
    contentText = content;
  } else {
    const firstItem = content?.[0];
    if (firstItem?.type === "text") {
      contentText = firstItem.text;
    }
  }

  // Extract node description from content (format: **Node Description**\n\nContent)
  // If content is empty, try to get node name from additional_kwargs
  let nodeDescription = "Processing";
  let nodeContent = "";
  
  if (contentText) {
    const parts = contentText.split("\n\n");
    nodeDescription = parts[0]?.replace(/\*\*/g, "") || "Processing";
    nodeContent = parts.slice(1).join("\n\n");
  } else {
    // If no content, try to get node name from additional_kwargs
    const additionalKwargs = (message as any).additional_kwargs;
    if (additionalKwargs?.nodeName) {
      nodeDescription = additionalKwargs.nodeName;
    }
  }
  
  // If still no description and no content, don't render
  if (!nodeDescription || nodeDescription === "Processing") {
    return <></>;
  }

  // Generate color based on node name for consistency (muted, subtle colors)
  const getNodeColor = (nodeName: string): string => {
    const colors = [
      "text-gray-600",
      "text-slate-600",
      "text-zinc-600",
      "text-neutral-600",
      "text-stone-600",
    ];
    let hash = 0;
    for (let i = 0; i < nodeName.length; i++) {
      hash = nodeName.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  };

  const nodeColor = getNodeColor(nodeDescription);

  return (
    <div className="w-full max-w-2xl py-2">
      <Accordion
        defaultValue={expandNodeAccordions ? `accordion-${id}` : undefined}
        type="single"
        collapsible
        className="w-full"
      >
        <AccordionItem value={`accordion-${id}`} className="border-none">
          <AccordionTrigger className={`text-sm font-medium ${nodeColor} hover:no-underline py-2 px-0`}>
            <span className="flex items-center gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-current opacity-40"></span>
              {nodeDescription}
            </span>
          </AccordionTrigger>
          <AccordionContent className="pt-2 pb-0 px-0">
            <div className="text-sm text-gray-700 whitespace-pre-wrap bg-gray-50 rounded-lg p-4 border border-gray-200">
              {nodeContent}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
};

const NodeProgressMessage = React.memo(NodeProgressMessageComponent);

export const AssistantMessage: FC<AssistantMessageProps> = ({
  runId,
  feedbackSubmitted,
  setFeedbackSubmitted,
}) => {
  let message;
  try {
    message = useMessage();
  } catch (error) {
    // Handle "Entry not available in the store" error gracefully
    console.warn("AssistantMessage: Failed to get message from store", error);
    return null;
  }
  
  if (!message || !message.id) {
    return null;
  }
  
  const { isLast } = message;
  const isThinkingMessage = message.id.startsWith("thinking-");
  const isWebSearchMessage = message.id.startsWith("web-search-results-");
  const isNodeProgressMessage = message.id.startsWith("node-progress-");

  if (isThinkingMessage) {
    return <ThinkingAssistantMessage message={message} />;
  }

  if (isWebSearchMessage) {
    return <WebSearchMessage message={message} />;
  }

  if (isNodeProgressMessage) {
    return <NodeProgressMessage message={message} />;
  }

  // Additional safety check - ensure message content is available
  if (!message.content) {
    return null;
  }

  return (
    <MessagePrimitive.Root className="relative grid w-full max-w-2xl grid-cols-[auto_auto_1fr] grid-rows-[auto_1fr] py-4">
      <Avatar className="col-start-1 row-span-full row-start-1 mr-4">
        <AvatarFallback>A</AvatarFallback>
      </Avatar>

      <div className="text-foreground col-span-2 col-start-2 row-start-1 my-1.5 max-w-xl break-words leading-7">
        <MessagePrimitive.Content components={{ Text: MarkdownText }} />
        {isLast && runId && (
          <MessagePrimitive.If lastOrHover assistant>
            <AssistantMessageBar
              feedbackSubmitted={feedbackSubmitted}
              setFeedbackSubmitted={setFeedbackSubmitted}
              runId={runId}
            />
          </MessagePrimitive.If>
        )}
      </div>
    </MessagePrimitive.Root>
  );
};

export const UserMessage: FC = () => {
  let msg;
  try {
    msg = useMessage(getExternalStoreMessage<HumanMessage>);
  } catch (error) {
    // Handle "Entry not available in the store" error gracefully
    console.warn("UserMessage: Failed to get message from store", error);
    return null;
  }
  
  const humanMessage = Array.isArray(msg) ? msg[0] : msg;

  // Return null if message is not available yet (prevents rendering issues on first message)
  if (!humanMessage) return null;

  // Check if this message has highlighted text
  const highlightedText = humanMessage.additional_kwargs?.highlightedText as
    | TextHighlight
    | undefined;
  const selectedText = highlightedText?.selectedText;

  return (
    <MessagePrimitive.Root className="grid w-full max-w-2xl auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] gap-y-2 py-4">
      <ContextDocumentsUI
        message={humanMessage}
        className="col-start-2 row-start-1"
      />
      {selectedText && (
        <div className="bg-blue-50 border border-blue-200 text-foreground col-start-2 row-start-2 max-w-xl break-words rounded-lg px-4 py-2 text-sm text-gray-600 italic">
          {selectedText}
        </div>
      )}
      <div
        className={`bg-muted text-foreground col-start-2 ${
          selectedText ? "row-start-3" : "row-start-2"
        } max-w-xl break-words rounded-3xl px-5 py-2.5`}
      >
        <MessagePrimitive.Content />
      </div>
    </MessagePrimitive.Root>
  );
};

interface AssistantMessageBarProps {
  runId: string;
  feedbackSubmitted: boolean;
  setFeedbackSubmitted: Dispatch<SetStateAction<boolean>>;
}

const AssistantMessageBarComponent = ({
  runId,
  feedbackSubmitted,
  setFeedbackSubmitted,
}: AssistantMessageBarProps) => {
  const { isLoading, sendFeedback } = useFeedback();
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="flex items-center mt-2"
    >
      {feedbackSubmitted ? (
        <TighterText className="text-gray-500 text-sm">
          Feedback received! Thank you!
        </TighterText>
      ) : (
        <>
          <ActionBarPrimitive.FeedbackPositive asChild>
            <FeedbackButton
              isLoading={isLoading}
              sendFeedback={sendFeedback}
              setFeedbackSubmitted={setFeedbackSubmitted}
              runId={runId}
              feedbackValue={1.0}
              icon="thumbs-up"
            />
          </ActionBarPrimitive.FeedbackPositive>
          <ActionBarPrimitive.FeedbackNegative asChild>
            <FeedbackButton
              isLoading={isLoading}
              sendFeedback={sendFeedback}
              setFeedbackSubmitted={setFeedbackSubmitted}
              runId={runId}
              feedbackValue={0.0}
              icon="thumbs-down"
            />
          </ActionBarPrimitive.FeedbackNegative>
        </>
      )}
    </ActionBarPrimitive.Root>
  );
};

const AssistantMessageBar = React.memo(AssistantMessageBarComponent);
