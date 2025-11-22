import {
  UsaFlag,
  KoreaFlag,
  IndiaFlag,
  SpanishFlag,
  FrenchFlag,
} from "@/components/icons/flags";
import { TooltipIconButton } from "@/components/ui/assistant-ui/tooltip-icon-button";
import { GraphInput } from "@/shared/types";
import { LanguageOptions } from "@/shared/types";

export interface TranslateOptionsProps {
  streamMessage: (params: GraphInput) => Promise<void>;
  handleClose: () => void;
}

export function TranslateOptions(props: TranslateOptionsProps) {
  const { streamMessage } = props;

  const handleSubmit = async (language: LanguageOptions) => {
    props.handleClose();
    await streamMessage({
      language,
    });
  };

  return (
    <div className="flex flex-col gap-3 items-center w-full">
      <TooltipIconButton
        tooltip="English"
        variant="ghost"
        className="transition-colors w-[36px] h-[36px]"
        delayDuration={400}
        onClick={async () => await handleSubmit("english")}
      >
        <UsaFlag />
      </TooltipIconButton>
      <TooltipIconButton
        tooltip="Korean"
        variant="ghost"
        className="transition-colors w-[36px] h-[36px]"
        delayDuration={400}
        onClick={async () => await handleSubmit("korean")}
      >
        <KoreaFlag />
      </TooltipIconButton>
   
      <TooltipIconButton
        tooltip="Spanish"
        variant="ghost"
        className="transition-colors w-[36px] h-[36px]"
        delayDuration={400}
        onClick={async () => await handleSubmit("spanish")}
      >
        <SpanishFlag />
      </TooltipIconButton>
      <TooltipIconButton
        tooltip="French"
        variant="ghost"
        className="transition-colors w-[36px] h-[36px]"
        delayDuration={400}
        onClick={async () => await handleSubmit("french")}
      >
        <FrenchFlag />
      </TooltipIconButton>
    </div>
  );
}
