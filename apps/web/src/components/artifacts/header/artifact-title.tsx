import { CircleCheck, CircleX, LoaderCircle } from "lucide-react";
import { ArtifactCode, ArtifactMarkdown } from "@/shared/types";
import { useMemo } from "react";

interface ArtifactTitleProps {
  title: string;
  isArtifactSaved: boolean;
  artifactUpdateFailed: boolean;
  content: ArtifactCode | ArtifactMarkdown;
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
    <div className="pl-[6px] pt-3 flex flex-col items-start justify-start ml-[6px] gap-1 max-w-1/2">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-medium text-gray-600 line-clamp-1">
          {props.title}
        </h1>
        <span className="text-sm font-light text-gray-400">
          ({characterCount.toLocaleString()} characters)
        </span>
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
