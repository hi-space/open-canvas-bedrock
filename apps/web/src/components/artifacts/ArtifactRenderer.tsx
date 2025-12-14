import { cn } from "@/lib/utils";
import {
  Artifact,
  ArtifactMarkdown,
} from "@/shared/types";
import React, { useEffect, useState } from "react";
import { ActionsToolbar } from "./actions_toolbar";
import { CustomQuickActions } from "./actions_toolbar/custom";
import { getArtifactContent } from "@/shared/utils/artifacts";
import { ArtifactLoading } from "./ArtifactLoading";
import { useGraphContext } from "@/contexts/GraphContext";
import { ArtifactHeader } from "./header";
import { useUserContext } from "@/contexts/UserContext";
import { useAssistantContext } from "@/contexts/AssistantContext";
import { ArtifactDiffViewer } from "./ArtifactDiffViewer";
import { ArtifactContent } from "./ArtifactContent";

export interface ArtifactRendererProps {
  isEditing: boolean;
  setIsEditing: React.Dispatch<React.SetStateAction<boolean>>;
  chatCollapsed: boolean;
  setChatCollapsed: (c: boolean) => void;
  hideHeader?: boolean; // For diff mode - hide header when used in split view
  hideToolbars?: boolean; // For diff mode - hide toolbars when used in split view
}

function ArtifactRendererComponent(props: ArtifactRendererProps) {
  const { graphData } = useGraphContext();
  const { selectedAssistant } = useAssistantContext();
  const { user } = useUserContext();
  const {
    artifact,
    selectedBlocks,
    isStreaming,
    isLoadingThread,
    isArtifactSaved,
    artifactUpdateFailed,
    setSelectedArtifact,
    streamMessage,
    setArtifact,
    chatStarted,
    isDiffMode,
    diffBaseVersionIndex,
    setIsDiffMode,
    setDiffBaseVersionIndex,
    refreshArtifactMetadata,
  } = graphData;
  const [isHoveringOverArtifact, setIsHoveringOverArtifact] = useState(false);
  
  // Create empty artifact if none exists (like "New Markdown" button)
  useEffect(() => {
    if (chatStarted && !artifact && !isStreaming) {
      const artifactContent: ArtifactMarkdown = {
        index: 1,
        type: "text",
        title: "새 문서",
        fullMarkdown: "",
      };

      const newArtifact: Artifact = {
        currentIndex: 1,
        contents: [artifactContent],
      };
      setArtifact(newArtifact);
      props.setIsEditing(true);
    }
  }, [chatStarted, artifact, isStreaming]);

  const currentArtifactContent = artifact
    ? getArtifactContent(artifact)
    : undefined;

  // Show loading spinner while loading thread or streaming
  if (isLoadingThread || (!artifact && isStreaming)) {
    return <ArtifactLoading />;
  }

  if (!artifact || !currentArtifactContent) {
    return <div className="w-full h-full"></div>;
  }

  // Get version metadata if available (from server)
  const versionMetadata = (artifact as any)._metadata;
  const totalVersions = versionMetadata?.total_versions || artifact.contents.length;
  const versionIndices = versionMetadata?.version_indices || artifact.contents.map((c) => c.index);
  
  // Sort version indices for navigation
  const sortedVersionIndices = [...versionIndices].sort((a, b) => a - b);
  const minIndex = sortedVersionIndices[0];
  const maxIndex = sortedVersionIndices[sortedVersionIndices.length - 1];
  
  // Helper function to find previous/next version index in the sorted array
  const getPreviousVersionIndex = (currentIndex: number): number | null => {
    const currentPos = sortedVersionIndices.indexOf(currentIndex);
    if (currentPos <= 0) return null;
    return sortedVersionIndices[currentPos - 1];
  };
  
  const getNextVersionIndex = (currentIndex: number): number | null => {
    const currentPos = sortedVersionIndices.indexOf(currentIndex);
    if (currentPos < 0 || currentPos >= sortedVersionIndices.length - 1) return null;
    return sortedVersionIndices[currentPos + 1];
  };
  
  // In diff mode, navigation controls the base version (left side)
  // In normal mode, navigation controls the current version
  const navigationIndex = isDiffMode && diffBaseVersionIndex !== undefined 
    ? diffBaseVersionIndex 
    : currentArtifactContent.index;
  
  const previousVersionIndex = getPreviousVersionIndex(navigationIndex);
  const nextVersionIndex = getNextVersionIndex(navigationIndex);
  
  const isBackwardsDisabled =
    totalVersions === 1 ||
    previousVersionIndex === null ||
    isStreaming;
  const isForwardDisabled =
    totalVersions === 1 ||
    (isDiffMode && diffBaseVersionIndex !== undefined && (nextVersionIndex === null || nextVersionIndex >= maxIndex)) ||
    (!isDiffMode && nextVersionIndex === null) ||
    isStreaming;

  // Show diff viewer if in diff mode and base version is set
  if (isDiffMode && diffBaseVersionIndex !== undefined && artifact) {
    // Get base version content for header display
    const baseVersionContent = artifact.contents.find((c) => c.index === diffBaseVersionIndex) || currentArtifactContent;
    
    return (
      <div className="relative w-full h-full max-h-screen overflow-auto">
        <ArtifactHeader
          isArtifactSaved={isArtifactSaved}
          isBackwardsDisabled={isBackwardsDisabled}
          isForwardDisabled={isForwardDisabled}
          setSelectedArtifact={
            // In diff mode, navigation changes the base version (left side)
            (index: number) => {
              if (isDiffMode && diffBaseVersionIndex !== undefined) {
                setDiffBaseVersionIndex(index);
              } else {
                setSelectedArtifact(index);
              }
            }
          }
          currentArtifactContent={baseVersionContent}
          totalArtifactVersions={totalVersions}
          previousVersionIndex={previousVersionIndex}
          nextVersionIndex={nextVersionIndex}
          selectedAssistant={selectedAssistant}
          artifactUpdateFailed={artifactUpdateFailed}
          chatCollapsed={props.chatCollapsed}
          setChatCollapsed={props.setChatCollapsed}
          isDiffMode={isDiffMode}
          setIsDiffMode={setIsDiffMode}
          setDiffBaseVersionIndex={setDiffBaseVersionIndex}
          refreshArtifactMetadata={refreshArtifactMetadata}
        />
        <ArtifactDiffViewer
          artifact={artifact}
          baseVersionIndex={diffBaseVersionIndex}
          isEditing={props.isEditing}
          isHovering={isHoveringOverArtifact}
          setIsEditing={props.setIsEditing}
          chatCollapsed={props.chatCollapsed}
          setChatCollapsed={props.setChatCollapsed}
        />
      </div>
    );
  }

  return (
    <div className="relative w-full h-full max-h-screen overflow-auto">
      {!props.hideHeader && (
        <ArtifactHeader
          isArtifactSaved={isArtifactSaved}
          isBackwardsDisabled={isBackwardsDisabled}
          isForwardDisabled={isForwardDisabled}
          setSelectedArtifact={setSelectedArtifact}
          currentArtifactContent={currentArtifactContent}
          totalArtifactVersions={totalVersions}
          previousVersionIndex={previousVersionIndex}
          nextVersionIndex={nextVersionIndex}
          selectedAssistant={selectedAssistant}
          artifactUpdateFailed={artifactUpdateFailed}
          chatCollapsed={props.chatCollapsed}
          setChatCollapsed={props.setChatCollapsed}
          isDiffMode={isDiffMode}
          setIsDiffMode={setIsDiffMode}
          setDiffBaseVersionIndex={setDiffBaseVersionIndex}
          refreshArtifactMetadata={refreshArtifactMetadata}
        />
      )}
      <div
        onMouseEnter={() => setIsHoveringOverArtifact(true)}
        onMouseLeave={() => setIsHoveringOverArtifact(false)}
      >
        <ArtifactContent
          isEditing={props.isEditing}
          isHovering={isHoveringOverArtifact}
        />
      </div>
      {!props.hideToolbars && (
        <>
          <CustomQuickActions
            streamMessage={streamMessage}
            assistantId={selectedAssistant?.assistant_id}
            user={user}
            isTextSelected={selectedBlocks !== undefined}
          />
          {currentArtifactContent.type === "text" ? (
            <ActionsToolbar
              streamMessage={streamMessage}
              isTextSelected={selectedBlocks !== undefined}
            />
          ) : null}
        </>
      )}
    </div>
  );
}

export const ArtifactRenderer = React.memo(ArtifactRendererComponent);
