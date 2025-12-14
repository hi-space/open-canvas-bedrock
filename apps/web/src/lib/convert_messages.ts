import {
  useExternalMessageConverter,
  ToolCallContentPart,
} from "@assistant-ui/react";
import { AIMessage, BaseMessage, ToolMessage } from "@langchain/core/messages";

type Message = useExternalMessageConverter.Message;


function getMessageContentOrThrow(message: unknown): string {
  if (typeof message !== "object" || message === null) {
    return "";
  }

  const castMsg = message as Record<string, any>;

  if (
    typeof castMsg?.content !== "string" &&
    (!Array.isArray(castMsg.content) || castMsg.content[0]?.type !== "text") &&
    (!castMsg.kwargs ||
      !castMsg.kwargs?.content ||
      typeof castMsg.kwargs?.content !== "string")
  ) {
    console.error(castMsg);
    throw new Error("Only text messages are supported");
  }

  let content = "";
  if (Array.isArray(castMsg.content) && castMsg.content[0]?.type === "text") {
    content = castMsg.content[0].text;
  } else if (typeof castMsg.content === "string") {
    content = castMsg.content;
  } else if (
    castMsg?.kwargs &&
    castMsg.kwargs?.content &&
    typeof castMsg.kwargs?.content === "string"
  ) {
    content = castMsg.kwargs.content;
  }

  return content;
}

export const convertLangchainMessages: useExternalMessageConverter.Callback<
  BaseMessage
> = (message): Message | Message[] => {
  // Validate message exists - return safe fallback instead of throwing
  if (!message) {
    console.error("convertLangchainMessages: message is null or undefined");
    const fallbackId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    return {
      role: "user",
      id: fallbackId,
      content: [{ type: "text", text: "" }],
    };
  }

  // Ensure message has a valid ID
  const messageId = message.id && typeof message.id === "string" && message.id.trim()
    ? message.id.trim()
    : `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  let content: string;
  try {
    content = getMessageContentOrThrow(message);
  } catch (error) {
    console.error("convertLangchainMessages: Failed to get message content", error, message);
    // Return a safe fallback message instead of throwing
    content = "";
  }

  try {
    switch (message.getType()) {
    case "system":
      return {
        role: "system",
        id: messageId,
        content: [{ type: "text", text: content }],
      };
    case "human":
      return {
        role: "user",
        id: messageId,
        content: [{ type: "text", text: content }],
        ...(message.additional_kwargs
          ? {
              metadata: {
                custom: {
                  ...message.additional_kwargs,
                },
              },
            }
          : {}),
      };
    case "ai":
      const aiMsg = message as AIMessage;
      const toolCallsContent: ToolCallContentPart[] = aiMsg.tool_calls?.length
        ? aiMsg.tool_calls.map((tc) => ({
            type: "tool-call" as const,
            toolCallId: tc.id ?? "",
            toolName: tc.name,
            args: tc.args,
            argsText: JSON.stringify(tc.args),
          }))
        : [];
      return {
        role: "assistant",
        id: messageId,
        content: [
          ...toolCallsContent,
          {
            type: "text",
            text: content,
          },
        ],
        ...(message.additional_kwargs
          ? {
              metadata: {
                custom: {
                  ...message.additional_kwargs,
                },
              },
            }
          : {}),
      };
    case "tool":
      return {
        role: "tool",
        toolName: message.name,
        toolCallId: (message as ToolMessage).tool_call_id,
        result: content,
      };
    default:
      console.error("convertLangchainMessages: Unsupported message type", message);
      // Return a safe fallback instead of throwing to prevent crashes
      return {
        role: "user",
        id: messageId,
        content: [{ type: "text", text: content || "" }],
      };
    }
  } catch (error) {
    console.error("convertLangchainMessages: Error converting message", error, message);
    // Return a safe fallback message to prevent crashes
    return {
      role: "user",
      id: messageId,
      content: [{ type: "text", text: content || "" }],
    };
  }
};

/**
 * BaseMessage를 plain object로 변환합니다.
 * type 필드를 명시적으로 추가합니다. */
export function serializeLangChainMessage(message: BaseMessage) {
  return {
    ...(message as any), // BaseMessage의 모든 enumerable 속성
    type: message.getType(), // type 필드 명시적으로 추가 (필수!)
  };
}

