import { ReflectionsDialog } from "../../reflections-dialog/ReflectionsDialog";
import { ArtifactTitle } from "./artifact-title";
import { NavigateArtifactHistory } from "./navigate-artifact-history";
import { ArtifactCode, ArtifactMarkdown } from "@/shared/types";
import { Assistant } from "@langchain/langgraph-sdk";
import { PanelRightClose, GitCompare } from "lucide-react";
import { TooltipIconButton } from "@/components/ui/assistant-ui/tooltip-icon-button";

interface ArtifactHeaderProps {
  isBackwardsDisabled: boolean;
  isForwardDisabled: boolean;
  setSelectedArtifact: (index: number) => void;
  currentArtifactContent: ArtifactCode | ArtifactMarkdown;
  isArtifactSaved: boolean;
  totalArtifactVersions: number;
  previousVersionIndex?: number | null;
  nextVersionIndex?: number | null;
  selectedAssistant: Assistant | undefined;
  artifactUpdateFailed: boolean;
  chatCollapsed: boolean;
  setChatCollapsed: (c: boolean) => void;
  isDiffMode: boolean;
  setIsDiffMode: (enabled: boolean) => void;
  setDiffBaseVersionIndex: (index: number | undefined) => void;
  refreshArtifactMetadata: () => Promise<void>;
}

export function ArtifactHeader(props: ArtifactHeaderProps) {
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
          isArtifactSaved={props.isArtifactSaved}
          artifactUpdateFailed={props.artifactUpdateFailed}
          content={props.currentArtifactContent}
        />
      </div>
      <div className="flex gap-2 items-end mt-[10px] mr-[6px]">
        {props.totalArtifactVersions > 1 && (
          <TooltipIconButton
            tooltip={props.isDiffMode ? "Exit comparison mode" : "Compare with previous version"}
            variant={props.isDiffMode ? "default" : "ghost"}
            delayDuration={400}
            onClick={async () => {
              if (props.isDiffMode) {
                props.setIsDiffMode(false);
                props.setDiffBaseVersionIndex(undefined);
                // Refresh metadata and load latest version when exiting diff mode
                await props.refreshArtifactMetadata();
              } else {
                // Enable diff mode and set base version to previous version
                // Use previousVersionIndex if available, otherwise fallback to index - 1
                const previousIndex = props.previousVersionIndex !== null && props.previousVersionIndex !== undefined
                  ? props.previousVersionIndex
                  : props.currentArtifactContent.index - 1;
                if (previousIndex !== null && previousIndex !== undefined && previousIndex >= 1) {
                  props.setIsDiffMode(true);
                  props.setDiffBaseVersionIndex(previousIndex);
                }
              }
            }}
            className="w-fit h-fit p-2"
          >
            <GitCompare className="w-5 h-5 text-gray-600" />
          </TooltipIconButton>
        )}
        <NavigateArtifactHistory
          isBackwardsDisabled={props.isBackwardsDisabled}
          isForwardDisabled={props.isForwardDisabled}
          setSelectedArtifact={props.setSelectedArtifact}
          currentArtifactIndex={props.currentArtifactContent.index}
          totalArtifactVersions={props.totalArtifactVersions}
          previousIndex={props.previousVersionIndex}
          nextIndex={props.nextVersionIndex}
        />
        <ReflectionsDialog selectedAssistant={props.selectedAssistant} />
      </div>
    </div>
  );
}
