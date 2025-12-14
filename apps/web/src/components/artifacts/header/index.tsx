import { ReflectionsDialog } from "../../reflections-dialog/ReflectionsDialog";
import { ArtifactTitle } from "./artifact-title";
import { NavigateArtifactHistory } from "./navigate-artifact-history";
import { ArtifactCode, ArtifactMarkdown } from "@/shared/types";
import { PanelRightClose, GitCompare } from "lucide-react";
import { TooltipIconButton } from "@/components/ui/assistant-ui/tooltip-icon-button";
import { useGraphContext } from "@/contexts/GraphContext";
import { useAssistantContext } from "@/contexts/AssistantContext";
import { useArtifactVersions } from "@/hooks/useArtifactVersions";

interface ArtifactHeaderProps {
  currentArtifactContent: ArtifactCode | ArtifactMarkdown;
  chatCollapsed: boolean;
  setChatCollapsed: (c: boolean) => void;
}

export function ArtifactHeader(props: ArtifactHeaderProps) {
  const { graphData } = useGraphContext();
  const { selectedAssistant } = useAssistantContext();
  const {
    artifact,
    isArtifactSaved,
    artifactUpdateFailed,
    isDiffMode,
    diffBaseVersionIndex,
    setIsDiffMode,
    setDiffBaseVersionIndex,
    setSelectedArtifact,
    refreshArtifactMetadata,
  } = graphData;

  // Get version metadata and navigation
  const { metadata, getVersionNavigation } = useArtifactVersions(artifact);
  
  // Calculate navigation index - use current content index if not in diff mode
  const navigationIndex =
    isDiffMode && diffBaseVersionIndex !== undefined
      ? diffBaseVersionIndex
      : props.currentArtifactContent.index;
  
  // Get navigation info - only call if metadata exists
  const navigation = metadata
    ? getVersionNavigation(navigationIndex, isDiffMode)
    : {
        previousIndex: null,
        nextIndex: null,
        isBackwardsDisabled: true,
        isForwardDisabled: true,
      };

  const handleDiffModeToggle = async () => {
    if (isDiffMode) {
      setIsDiffMode(false);
      setDiffBaseVersionIndex(undefined);
      await refreshArtifactMetadata();
    } else {
      // Enable diff mode and set base version to previous version
      // Calculate previous index safely
      let previousIndex: number | null = null;
      
      if (metadata && metadata.totalVersions > 1) {
        const currentNav = getVersionNavigation(
          props.currentArtifactContent.index,
          false
        );
        previousIndex = currentNav.previousIndex; // Use previousIndex, not previousVersionIndex
      }
      
      // Fallback to index - 1 if navigation doesn't provide it
      if (previousIndex === null || previousIndex === undefined) {
        const fallbackIndex = props.currentArtifactContent.index - 1;
        if (fallbackIndex >= 1) {
          previousIndex = fallbackIndex;
        }
      }
      
      // Enable diff mode if we have a valid previous index
      if (previousIndex !== null && previousIndex !== undefined && previousIndex >= 1) {
        setIsDiffMode(true);
        setDiffBaseVersionIndex(previousIndex);
      }
    }
  };

  const handleVersionNavigation = (index: number) => {
    if (isDiffMode && diffBaseVersionIndex !== undefined) {
      setDiffBaseVersionIndex(index);
    } else {
      setSelectedArtifact(index);
    }
  };

  return (
    <div className="flex flex-row items-center justify-between">
      <div className="flex flex-row items-center justify-center gap-2">
        {props.chatCollapsed && (
          <TooltipIconButton
            tooltip="Expand Chat"
            variant="ghost"
            className="ml-2 mb-1 w-8 h-8"
            delayDuration={400}
            onClick={() => props.setChatCollapsed(false)}
          >
            <PanelRightClose className="text-gray-600" />
          </TooltipIconButton>
        )}
        <ArtifactTitle
          title={props.currentArtifactContent.title}
          isArtifactSaved={isArtifactSaved}
          artifactUpdateFailed={artifactUpdateFailed}
          content={props.currentArtifactContent}
        />
      </div>
      <div className="flex gap-2 items-end mt-[10px] mr-[6px]">
        {metadata && metadata.totalVersions > 1 && (
          <TooltipIconButton
            tooltip={
              isDiffMode
                ? "Exit comparison mode"
                : "Compare with previous version"
            }
            variant={isDiffMode ? "default" : "ghost"}
            delayDuration={400}
            onClick={handleDiffModeToggle}
            className="w-fit h-fit p-2"
          >
            <GitCompare className="w-5 h-5 text-gray-600" />
          </TooltipIconButton>
        )}
        {metadata && (
          <NavigateArtifactHistory
            isBackwardsDisabled={navigation.isBackwardsDisabled}
            isForwardDisabled={navigation.isForwardDisabled}
            setSelectedArtifact={handleVersionNavigation}
            currentArtifactIndex={props.currentArtifactContent.index}
            totalArtifactVersions={metadata.totalVersions}
            previousIndex={navigation.previousVersionIndex}
            nextIndex={navigation.nextVersionIndex}
          />
        )}
        <ReflectionsDialog selectedAssistant={selectedAssistant} />
      </div>
    </div>
  );
}
