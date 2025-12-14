import { CircleCheck, CircleX, LoaderCircle, FileText, GitBranch } from "lucide-react";
import { ArtifactCode, ArtifactMarkdown } from "@/shared/types";
import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";

interface ArtifactTitleProps {
  title: string;
  isArtifactSaved: boolean;
  artifactUpdateFailed: boolean;
  content: ArtifactCode | ArtifactMarkdown;
  versionInfo?: {
    currentVersion: number;
    totalVersions: number;
  };
}

export function ArtifactTitle(props: ArtifactTitleProps) {
  const characterCount = useMemo(() => {
    if (props.content.type === "text") {
      return props.content.fullMarkdown.length;
    } else {
      return props.content.code.length;
    }
  }, [props.content]);

  return (
    <div className="pl-[6px] pt-3 flex flex-col items-start justify-start ml-[6px] gap-2 max-w-1/2">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-medium text-gray-600 line-clamp-1">
          {props.title}
        </h1>
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline" className="text-xs font-normal text-gray-500 border-gray-300 bg-gray-50/50">
            <FileText className="w-3 h-3 mr-1.5" />
            {characterCount.toLocaleString()}자
          </Badge>
          {props.versionInfo && (
            <Badge variant="outline" className="text-xs font-normal text-gray-500 border-gray-300 bg-gray-50/50">
              <GitBranch className="w-3 h-3 mr-1.5" />
              v{props.versionInfo.currentVersion} / {props.versionInfo.totalVersions}
            </Badge>
          )}
        </div>
      </div>
      <span className="mt-auto">
        {props.isArtifactSaved ? (
          <span className="flex items-center justify-start gap-1 text-gray-400">
            <p className="text-xs font-light">Saved</p>
            <CircleCheck className="w-[10px] h-[10px]" />
          </span>
        ) : !props.artifactUpdateFailed ? (
          <span className="flex items-center justify-start gap-1 text-gray-400">
            <p className="text-xs font-light">Saving</p>
            <LoaderCircle className="animate-spin w-[10px] h-[10px]" />
          </span>
        ) : props.artifactUpdateFailed ? (
          <span className="flex items-center justify-start gap-1 text-red-300">
            <p className="text-xs font-light">Failed to save</p>
            <CircleX className="w-[10px] h-[10px]" />
          </span>
        ) : null}
      </span>
    </div>
  );
}
