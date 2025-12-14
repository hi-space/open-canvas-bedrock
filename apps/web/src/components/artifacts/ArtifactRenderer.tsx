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
import { useArtifactVersions } from "@/hooks/useArtifactVersions";

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
  
  // Use version management hook - MUST be called before any early returns
  const { metadata, getVersionNavigation, getVersionContent } =
    useArtifactVersions(artifact);
  
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

  // In diff mode, navigation controls the base version (left side)
  // In normal mode, navigation controls the current version
  const navigationIndex =
    isDiffMode && diffBaseVersionIndex !== undefined
      ? diffBaseVersionIndex
      : currentArtifactContent.index;

  const navigation = getVersionNavigation(navigationIndex, isDiffMode);
  const { previousVersionIndex, nextVersionIndex, isBackwardsDisabled: navBackwardsDisabled, isForwardDisabled: navForwardDisabled } = navigation;

  const isBackwardsDisabled = navBackwardsDisabled || isStreaming;
  const isForwardDisabled = navForwardDisabled || isStreaming;

  // Show diff viewer if in diff mode and base version is set
  if (isDiffMode && diffBaseVersionIndex !== undefined && artifact) {
    // Get base version content for header display
    const baseVersionContent =
      getVersionContent(diffBaseVersionIndex) || currentArtifactContent;

    return (
      <div className="relative w-full h-full max-h-screen overflow-auto">
        <ArtifactHeader
          currentArtifactContent={baseVersionContent}
          chatCollapsed={props.chatCollapsed}
          setChatCollapsed={props.setChatCollapsed}
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
          currentArtifactContent={currentArtifactContent}
          chatCollapsed={props.chatCollapsed}
          setChatCollapsed={props.setChatCollapsed}
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
