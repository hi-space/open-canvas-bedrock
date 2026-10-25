"use client";

import { BookOpenText } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TooltipIconButton } from "../assistant-ui/tooltip-icon-button";
import { useGraphContext } from "@/contexts/GraphContext";
import { ResearchGenre } from "@/shared/types";
import { cn } from "@/lib/utils";

export const RESEARCH_GENRES: { value: ResearchGenre; label: string; description: string }[] = [
  { value: "paper", label: "논문", description: "깊은 조사, 엄밀한 구조와 참고문헌" },
  { value: "blog", label: "블로그", description: "실무자를 위한 기술 해설" },
  { value: "linkedin", label: "LinkedIn", description: "핵심 인사이트 한 가지" },
];

interface ResearchGenreSelectProps {
  className?: string;
  onOpenChange?: (isOpen: boolean) => void;
}

export function ResearchGenreSelect(props: ResearchGenreSelectProps) {
  const {
    graphData: { researchGenre, setResearchGenre },
  } = useGraphContext();
  const active = RESEARCH_GENRES.find((g) => g.value === researchGenre);

  return (
    <DropdownMenu onOpenChange={props.onOpenChange}>
      <DropdownMenuTrigger asChild>
        <TooltipIconButton
          tooltip={active ? `딥 리서치: ${active.label}` : "딥 리서치 작성"}
          variant="ghost"
          className={cn("size-7 flex-shrink-0", props.className)}
        >
          <BookOpenText />
        </TooltipIconButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>딥 리서치 후 작성</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={researchGenre ?? "off"}
          onValueChange={(value) =>
            setResearchGenre(value === "off" ? undefined : (value as ResearchGenre))
          }
        >
          <DropdownMenuRadioItem value="off">끄기</DropdownMenuRadioItem>
          {RESEARCH_GENRES.map((genre) => (
            <DropdownMenuRadioItem key={genre.value} value={genre.value}>
              <div className="flex flex-col">
                <span>{genre.label}</span>
                <span className="text-xs text-muted-foreground">{genre.description}</span>
              </div>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
