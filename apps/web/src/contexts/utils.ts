import { cleanContent } from "@/lib/normalize_string";
import {
  Artifact,
  ArtifactCode,
  ArtifactMarkdown,
  ArtifactToolResponse,
  ProgrammingLanguageOptions,
  RewriteArtifactMetaToolResponse,
} from "@/shared/types";
import {
  AIMessage,
  BaseMessage,
  BaseMessageChunk,
} from "@langchain/core/messages";
import { parsePartialJson } from "@langchain/core/output_parsers";

export function removeCodeBlockFormatting(text: string): string {
  if (!text) return text;
  // Regular expression to match code blocks
  const codeBlockRegex = /^```[\w-]*\n([\s\S]*?)\n```$/;

  // Check if the text matches the code block pattern
  const match = text.match(codeBlockRegex);

  if (match) {
    // If it matches, return the content inside the code block
    return match[1].trim();
  } else {
    // If it doesn't match, return the original text
    return text;
  }
}

export const replaceOrInsertMessageChunk = (
  prevMessages: BaseMessage[],
  newMessageChunk: BaseMessageChunk
): BaseMessage[] => {
  const existingMessageIndex = prevMessages.findIndex(
    (msg) => msg.id === newMessageChunk.id
  );

  if (
    prevMessages[existingMessageIndex]?.content &&
    typeof prevMessages[existingMessageIndex]?.content !== "string"
  ) {
    throw new Error("Message content is not a string");
  }
  if (typeof newMessageChunk.content !== "string") {
    throw new Error("Message chunk content is not a string");
  }

  if (existingMessageIndex !== -1) {
    // Create a new array with the updated message
    return [
      ...prevMessages.slice(0, existingMessageIndex),
      new AIMessage({
        ...prevMessages[existingMessageIndex],
        content:
          (prevMessages[existingMessageIndex]?.content || "") +
          (newMessageChunk?.content || ""),
      }),
      ...prevMessages.slice(existingMessageIndex + 1),
    ];
  } else {
    const newMessage = new AIMessage({
      ...newMessageChunk,
    });
    return [...prevMessages, newMessage];
  }
};

export const createNewGeneratedArtifactFromTool = (
  artifactTool: ArtifactToolResponse
): ArtifactMarkdown | ArtifactCode | undefined => {
  if (!artifactTool.type) {
    console.error("Received new artifact without type");
    return;
  }
  if (artifactTool.type === "text") {
    return {
      index: 1,
      type: "text",
      title: artifactTool.title || "",
      fullMarkdown: artifactTool.artifact || "",
    };
  } else {
    if (!artifactTool.language) {
      console.error("Received new code artifact without language");
    }
    return {
      index: 1,
      type: "code",
      title: artifactTool.title || "",
      code: artifactTool.artifact || "",
      language: artifactTool.language as ProgrammingLanguageOptions,
    };
  }
};

const validateNewArtifactIndex = (
  newArtifactIndexGuess: number,
  prevArtifactContentsLength: number,
  isFirstUpdate: boolean
): number => {
  if (isFirstUpdate) {
    // For first updates, currentIndex should be one more than the total prev contents
    // to append the new content at the end
    if (newArtifactIndexGuess !== prevArtifactContentsLength + 1) {
      return prevArtifactContentsLength + 1;
    }
  } else {
    if (newArtifactIndexGuess !== prevArtifactContentsLength) {
      // For subsequent updates, currentIndex should match the total contents
      // to update the latest content in place
      return prevArtifactContentsLength;
    }
  }
  // If the guess is correct, return the guess
  return newArtifactIndexGuess;
};

export const updateHighlightedMarkdown = (
  prevArtifact: Artifact,
  content: string,
  newArtifactIndex: number,
  prevCurrentContent: ArtifactMarkdown,
  isFirstUpdate: boolean
): Artifact | undefined => {
  // Create a deep copy of the previous artifact
  const basePrevArtifact = {
    ...prevArtifact,
    contents: prevArtifact.contents.map((c) => ({ ...c })),
  };

  const currentIndex = validateNewArtifactIndex(
    newArtifactIndex,
    basePrevArtifact.contents.length,
    isFirstUpdate
  );

  let newContents: (ArtifactCode | ArtifactMarkdown)[];

  if (isFirstUpdate) {
    const newMarkdownContent: ArtifactMarkdown = {
      ...prevCurrentContent,
      index: currentIndex,
      fullMarkdown: content,
    };
    newContents = [...basePrevArtifact.contents, newMarkdownContent];
  } else {
    newContents = basePrevArtifact.contents.map((c) => {
      if (c.index === currentIndex) {
        return {
          ...c,
          fullMarkdown: content,
        };
      }
      return { ...c }; // Create new reference for unchanged items too
    });
  }

  // Create new reference for the entire artifact
  const newArtifact: Artifact = {
    ...basePrevArtifact,
    currentIndex,
    contents: newContents,
  };

  // Verify we're actually creating a new reference
  if (Object.is(newArtifact, prevArtifact)) {
    console.warn("Warning: updateHighlightedMarkdown returned same reference");
  }

  return newArtifact;
};

export const updateHighlightedCode = (
  prevArtifact: Artifact,
  content: string,
  newArtifactIndex: number,
  prevCurrentContent: ArtifactCode,
  isFirstUpdate: boolean
): Artifact | undefined => {
  // Create a deep copy of the previous artifact
  const basePrevArtifact = {
    ...prevArtifact,
    contents: prevArtifact.contents.map((c) => ({ ...c })),
  };

  const currentIndex = validateNewArtifactIndex(
    newArtifactIndex,
    basePrevArtifact.contents.length,
    isFirstUpdate
  );

  let newContents: (ArtifactCode | ArtifactMarkdown)[];

  if (isFirstUpdate) {
    const newCodeContent: ArtifactCode = {
      ...prevCurrentContent,
      index: currentIndex,
      code: content,
    };
    newContents = [...basePrevArtifact.contents, newCodeContent];
  } else {
    newContents = basePrevArtifact.contents.map((c) => {
      if (c.index === currentIndex) {
        return {
          ...c,
          code: content,
        };
      }
      return { ...c }; // Create new reference for unchanged items too
    });
  }

  const newArtifact: Artifact = {
    ...basePrevArtifact,
    currentIndex,
    contents: newContents,
  };

  // Verify we're actually creating a new reference
  if (Object.is(newArtifact, prevArtifact)) {
    console.warn("Warning: updateHighlightedCode returned same reference");
  }

  return newArtifact;
};

interface UpdateRewrittenArtifactArgs {
  prevArtifact: Artifact;
  newArtifactContent: string;
  rewriteArtifactMeta: RewriteArtifactMetaToolResponse;
  prevCurrentContent?: ArtifactMarkdown | ArtifactCode;
  newArtifactIndex: number;
  isFirstUpdate: boolean;
  artifactLanguage: string;
}

export const updateRewrittenArtifact = ({
  prevArtifact,
  newArtifactContent,
  rewriteArtifactMeta,
  prevCurrentContent,
  newArtifactIndex,
  isFirstUpdate,
  artifactLanguage,
}: UpdateRewrittenArtifactArgs): Artifact => {
  // Create a deep copy of the previous artifact
  const basePrevArtifact = {
    ...prevArtifact,
    contents: prevArtifact.contents.map((c) => ({ ...c })),
  };

  const currentIndex = validateNewArtifactIndex(
    newArtifactIndex,
    basePrevArtifact.contents.length,
    isFirstUpdate
  );

  let artifactContents: (ArtifactMarkdown | ArtifactCode)[];

  if (isFirstUpdate) {
    if (rewriteArtifactMeta.type === "code") {
      artifactContents = [
        ...basePrevArtifact.contents,
        {
          type: "code",
          title: rewriteArtifactMeta.title || prevCurrentContent?.title || "",
          index: currentIndex,
          language: artifactLanguage as ProgrammingLanguageOptions,
          code: newArtifactContent,
        },
      ];
    } else {
      artifactContents = [
        ...basePrevArtifact.contents,
        {
          index: currentIndex,
          type: "text",
          title: rewriteArtifactMeta?.title ?? prevCurrentContent?.title ?? "",
          fullMarkdown: newArtifactContent,
        },
      ];
    }
  } else {
    if (rewriteArtifactMeta?.type === "code") {
      artifactContents = basePrevArtifact.contents.map((c) => {
        if (c.index === currentIndex) {
          return {
            ...c,
            code: newArtifactContent,
          };
        }
        return { ...c }; // Create new reference for unchanged items too
      });
    } else {
      artifactContents = basePrevArtifact.contents.map((c) => {
        if (c.index === currentIndex) {
          return {
            ...c,
            fullMarkdown: newArtifactContent,
          };
        }
        return { ...c }; // Create new reference for unchanged items too
      });
    }
  }

  const newArtifact: Artifact = {
    ...basePrevArtifact,
    currentIndex,
    contents: artifactContents,
  };

  // Verify we're actually creating a new reference
  if (Object.is(newArtifact, prevArtifact)) {
    console.warn("Warning: updateRewrittenArtifact returned same reference");
  }

  return newArtifact;
};

export function handleGenerateArtifactToolCallChunk(toolCallChunkArgs: string) {
  let newArtifactText: ArtifactToolResponse | undefined = undefined;

  // Attempt to parse the tool call chunk.
  try {
    newArtifactText = parsePartialJson(toolCallChunkArgs);
    if (!newArtifactText) {
      throw new Error("Failed to parse new artifact text");
    }
    newArtifactText = {
      ...newArtifactText,
      title: newArtifactText.title ?? "",
      type: newArtifactText.type ?? "",
    };
  } catch (_) {
    return "continue";
  }

  if (
    newArtifactText.artifact &&
    (newArtifactText.type === "text" ||
      (newArtifactText.type === "code" && newArtifactText.language))
  ) {
    const content = createNewGeneratedArtifactFromTool(newArtifactText);
    if (!content) {
      return undefined;
    }
    if (content.type === "text") {
      content.fullMarkdown = cleanContent(content.fullMarkdown);
    }

    return {
      currentIndex: 1,
      contents: [content],
    };
  }
}

type StreamChunkFields = {
  runId: string | undefined;
  event: string;
  langgraphNode: string;
  nodeInput: any | undefined;
  nodeChunk: any | undefined;
  nodeOutput: any | undefined;
  taskName: string | undefined;
};

export function extractChunkFields(
  chunk: Record<string, any> | undefined
): StreamChunkFields {
  if (!chunk || !chunk.data) {
    return {
      runId: undefined,
      event: "",
      langgraphNode: "",
      nodeInput: undefined,
      nodeChunk: undefined,
      nodeOutput: undefined,
      taskName: undefined,
    };
  }

  return {
    runId: chunk.data?.metadata?.run_id,
    event: chunk.data?.event || "",
    langgraphNode: chunk.data?.metadata?.langgraph_node || "",
    nodeInput: chunk.data?.data?.input,
    nodeChunk: chunk.data?.data?.chunk,
    nodeOutput: chunk.data?.data?.output,
    taskName: chunk.data?.name,
  };
}
