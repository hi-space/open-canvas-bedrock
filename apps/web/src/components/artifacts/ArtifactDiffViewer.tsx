import React, { useEffect, useRef, useMemo } from "react";
import { diff_match_patch as DiffMatchPatch } from "diff-match-patch";
import { Artifact, ArtifactMarkdown, ArtifactCode } from "@/shared/types";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useGraphContext } from "@/contexts/GraphContext";
import { useThreadContext } from "@/contexts/ThreadProvider";
import { API_URL } from "@/constants";
import { TextRenderer } from "./TextRenderer";
import { ArtifactContent } from "./ArtifactContent";
import { ActionsToolbar } from "./actions_toolbar";
import { CustomQuickActions } from "./actions_toolbar/custom";
import { useUserContext } from "@/contexts/UserContext";
import { useAssistantContext } from "@/contexts/AssistantContext";
import { getArtifactContent } from "@/shared/utils/artifacts";

interface ArtifactDiffViewerProps {
  artifact: Artifact;
  baseVersionIndex: number;
  isEditing: boolean;
  isHovering: boolean;
  setIsEditing: React.Dispatch<React.SetStateAction<boolean>>;
  chatCollapsed: boolean;
  setChatCollapsed: (c: boolean) => void;
}

/**
 * Extracts plain text content from artifact for diff comparison
 */
function getArtifactTextContent(content: ArtifactMarkdown | ArtifactCode): string {
  if (content.type === "text") {
    return content.fullMarkdown || "";
  } else if (content.type === "code") {
    return content.code || "";
  }
  return "";
}

/**
 * Renders read-only content for left side (base version)
 */
function BaseVersionRenderer({
  content,
  artifactType,
  isHovering,
}: {
  content: ArtifactMarkdown | ArtifactCode;
  artifactType: "text" | "code";
  isHovering: boolean;
}) {
  if (artifactType === "text" && content.type === "text") {
    return (
      <TextRenderer
        isInputVisible={false}
        isEditing={false}
        isHovering={isHovering}
        contentOverride={content}
        readOnly={true}
      />
    );
  } else if (artifactType === "code" && content.type === "code") {
    return (
      <div className="w-full h-full overflow-auto px-4 py-5 font-mono text-sm">
        <SyntaxHighlighter
          style={oneDark}
          language={content.language}
          PreTag="div"
          customStyle={{
            margin: 0,
            padding: "1rem",
            background: "transparent",
          }}
        >
          {content.code}
        </SyntaxHighlighter>
      </div>
    );
  }

  return null;
}

export function ArtifactDiffViewer({
  artifact,
  baseVersionIndex,
  isEditing,
  isHovering,
  setIsEditing,
  chatCollapsed,
  setChatCollapsed,
}: ArtifactDiffViewerProps) {
  const leftScrollRef = useRef<HTMLDivElement>(null);
  const rightScrollRef = useRef<HTMLDivElement>(null);
  const [isScrolling, setIsScrolling] = React.useState(false);
  const [isLoadingBaseVersion, setIsLoadingBaseVersion] = React.useState(false);
  const { graphData } = useGraphContext();
  const { setArtifact, selectedBlocks, streamMessage, artifact: contextArtifact } = graphData;
  const { threadId } = useThreadContext();
  const { user } = useUserContext();
  const { selectedAssistant } = useAssistantContext();

  // Get both versions
  const baseContent = artifact.contents.find((c) => c.index === baseVersionIndex);
  
  // Right side always shows the latest version (highest index)
  const versionMetadata = (artifact as any)._metadata;
  const versionIndices = versionMetadata?.version_indices || artifact.contents.map((c) => c.index);
  const latestVersionIndex = Math.max(...versionIndices);
  const currentContent = artifact.contents.find((c) => c.index === latestVersionIndex);

  // Auto-load base version if not loaded (without changing currentIndex)
  useEffect(() => {
    if (!baseContent && baseVersionIndex && threadId) {
      setIsLoadingBaseVersion(true);
      const loadBaseVersion = async () => {
        try {
          const response = await fetch(
            `${API_URL}/api/threads/${threadId}/artifact/versions/${baseVersionIndex}`
          );
          
          if (response.ok) {
            const versionArtifact = await response.json();
            const newContent = versionArtifact.contents?.[0];
            
            if (newContent) {
              setArtifact((prev) => {
                if (!prev) return prev;
                
                // Check if this version already exists
                const existingIndex = prev.contents.findIndex((c: any) => c.index === baseVersionIndex);
                let updatedContents;
                
                if (existingIndex >= 0) {
                  // Replace existing version
                  updatedContents = [...prev.contents];
                  updatedContents[existingIndex] = newContent;
                } else {
                  // Add new version
                  updatedContents = [...prev.contents, newContent];
                }
                
                // Don't change currentIndex - keep it as is to preserve the latest version display
                return {
                  ...prev,
                  contents: updatedContents,
                  // Explicitly preserve currentIndex
                  currentIndex: prev.currentIndex,
                };
              });
            }
          }
        } catch (error) {
          console.error("Failed to load base version:", error);
        } finally {
          setIsLoadingBaseVersion(false);
        }
      };
      
      loadBaseVersion();
    } else {
      setIsLoadingBaseVersion(false);
    }
  }, [baseContent, baseVersionIndex, threadId, setArtifact]);

  // Compute diff
  const diffOps = useMemo(() => {
    if (!baseContent || !currentContent) return [];

    const baseText = getArtifactTextContent(baseContent);
    const currentText = getArtifactTextContent(currentContent);

    const dmp = new DiffMatchPatch();
    const diffs = dmp.diff_main(baseText, currentText);
    dmp.diff_cleanupSemantic(diffs);

    return diffs;
  }, [baseContent, currentContent]);

  // Synchronized scrolling between left and right panels
  useEffect(() => {
    if (isScrolling) return;

    const leftEl = leftScrollRef.current;
    const rightEl = rightScrollRef.current;

    if (!leftEl || !rightEl) return;

    const handleLeftScroll = () => {
      if (isScrolling) return;
      setIsScrolling(true);
      const scrollRatio = leftEl.scrollTop / (leftEl.scrollHeight - leftEl.clientHeight);
      rightEl.scrollTop = scrollRatio * (rightEl.scrollHeight - rightEl.clientHeight);
      setTimeout(() => setIsScrolling(false), 50);
    };

    const handleRightScroll = () => {
      if (isScrolling) return;
      setIsScrolling(true);
      const scrollRatio = rightEl.scrollTop / (rightEl.scrollHeight - rightEl.clientHeight);
      leftEl.scrollTop = scrollRatio * (leftEl.scrollHeight - leftEl.clientHeight);
      setTimeout(() => setIsScrolling(false), 50);
    };

    leftEl.addEventListener("scroll", handleLeftScroll);
    rightEl.addEventListener("scroll", handleRightScroll);

    return () => {
      leftEl.removeEventListener("scroll", handleLeftScroll);
      rightEl.removeEventListener("scroll", handleRightScroll);
    };
  }, [isScrolling]);

  if (!baseContent || !currentContent) {
    // Show loading state if base version is being loaded
    if (isLoadingBaseVersion) {
      return (
        <div className="w-full h-full flex items-center justify-center text-gray-500">
          Loading version {baseVersionIndex}...
        </div>
      );
    }
    
    // Check if base version index is valid
    const isValidBaseIndex = versionIndices.includes(baseVersionIndex);
    if (!isValidBaseIndex && baseVersionIndex) {
      return (
        <div className="w-full h-full flex items-center justify-center text-gray-500">
          Version {baseVersionIndex} not found. Available versions: {versionIndices.join(", ")}
        </div>
      );
    }
    
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-500">
        One or both versions not found
      </div>
    );
  }

  // Check if both are same type
  if (baseContent.type !== currentContent.type) {
    return (
      <div className="w-full h-full flex items-center justify-center text-gray-500">
        Cannot compare different artifact types
      </div>
    );
  }

  const artifactType = baseContent.type === "text" ? "text" : "code";

  // Split the diff operations for left and right sides
  const leftDiffOps = diffOps.map(([op, text]) => {
    // Left side shows: unchanged (0) and deleted (-1)
    if (op === 0 || op === -1) {
      return [op, text] as [number, string];
    }
    return [0, ""] as [number, string];
  });

  const rightDiffOps = diffOps.map(([op, text]) => {
    // Right side shows: unchanged (0) and added (1)
    if (op === 0 || op === 1) {
      return [op, text] as [number, string];
    }
    return [0, ""] as [number, string];
  });

  return (
    <div className="w-full h-full flex flex-row border-t-[1px] border-gray-200">
      {/* Left side - Base version */}
      <div className="flex-1 flex flex-col border-r-[1px] border-gray-300 relative">
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-700 sticky top-0 z-10">
          Version {baseVersionIndex} (Previous)
        </div>
        <div
          ref={leftScrollRef}
          className="flex-1 overflow-auto relative"
        >
          <BaseVersionRenderer
            content={baseContent}
            artifactType={artifactType}
            isHovering={isHovering}
          />
        </div>
      </div>

      {/* Right side - Current version (uses ArtifactContent with all features) */}
      <div className="flex-1 flex flex-col relative">
        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-sm font-medium text-gray-700 sticky top-0 z-10">
          Version {latestVersionIndex} (Latest)
        </div>
        <div className="flex-1 relative">
          <ArtifactContent
            isEditing={isEditing}
            isHovering={isHovering}
            scrollContainerRef={rightScrollRef}
            forceVersionIndex={latestVersionIndex}
          />
        </div>
      </div>
      {/* Toolbars for current version (right side) */}
      <CustomQuickActions
        streamMessage={streamMessage}
        assistantId={selectedAssistant?.assistant_id}
        user={user}
        isTextSelected={selectedBlocks !== undefined}
      />
      {artifactType === "text" ? (
        <ActionsToolbar
          streamMessage={streamMessage}
          isTextSelected={selectedBlocks !== undefined}
        />
      ) : null}
    </div>
  );
}
