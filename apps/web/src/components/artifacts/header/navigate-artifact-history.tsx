import { TooltipIconButton } from "@/components/ui/assistant-ui/tooltip-icon-button";
import { Forward } from "lucide-react";

interface NavigateArtifactHistoryProps {
  isBackwardsDisabled: boolean;
  isForwardDisabled: boolean;
  setSelectedArtifact: (index: number) => void;
  currentArtifactIndex: number;
  totalArtifactVersions: number;
  previousIndex?: number | null; // Previous version index (if available)
  nextIndex?: number | null; // Next version index (if available)
}

export function NavigateArtifactHistory(props: NavigateArtifactHistoryProps) {
  // Use provided indices if available, otherwise calculate (for backward compatibility)
  const prevIndex = props.previousIndex !== undefined ? props.previousIndex : props.currentArtifactIndex - 1;
  const nextIndex = props.nextIndex !== undefined ? props.nextIndex : props.currentArtifactIndex + 1;
  
  const prevTooltip = prevIndex !== null && prevIndex !== undefined
    ? `Previous (${prevIndex}/${props.totalArtifactVersions})`
    : "Previous";
  const nextTooltip = nextIndex !== null && nextIndex !== undefined
    ? `Next (${nextIndex}/${props.totalArtifactVersions})`
    : "Next";

  return (
    <div className="flex items-center justify-center gap-1">
      <TooltipIconButton
        tooltip={prevTooltip}
        side="left"
        variant="ghost"
        delayDuration={400}
        onClick={() => {
          if (!props.isBackwardsDisabled && prevIndex !== null && prevIndex !== undefined) {
            props.setSelectedArtifact(prevIndex);
          }
        }}
        disabled={props.isBackwardsDisabled}
        className="w-fit h-fit p-2"
      >
        <Forward
          aria-disabled={props.isBackwardsDisabled}
          className="w-6 h-6 text-gray-600 scale-x-[-1]"
        />
      </TooltipIconButton>
      <TooltipIconButton
        tooltip={nextTooltip}
        variant="ghost"
        side="right"
        delayDuration={400}
        onClick={() => {
          if (!props.isForwardDisabled && nextIndex !== null && nextIndex !== undefined) {
            props.setSelectedArtifact(nextIndex);
          }
        }}
        disabled={props.isForwardDisabled}
        className="w-fit h-fit p-2"
      >
        <Forward
          aria-disabled={props.isForwardDisabled}
          className="w-6 h-6 text-gray-600"
        />
      </TooltipIconButton>
    </div>
  );
}
