import { Dispatch, SetStateAction, useEffect, useRef, useState, forwardRef, useMemo } from "react";
import { ArtifactMarkdown } from "@/shared/types";
import "@blocknote/core/fonts/inter.css";
import {
  getDefaultReactSlashMenuItems,
  SuggestionMenuController,
  useCreateBlockNote,
} from "@blocknote/react";
import { BlockNoteView } from "@blocknote/shadcn";
import "@blocknote/shadcn/style.css";
import { isArtifactMarkdownContent } from "@/shared/utils/artifacts";
import { CopyText } from "./components/CopyText";
import { getArtifactContent } from "@/shared/utils/artifacts";
import { useGraphContext } from "@/contexts/GraphContext";
import React from "react";
import { TooltipIconButton } from "../ui/assistant-ui/tooltip-icon-button";
import { Eye, EyeOff } from "lucide-react";
import { motion } from "framer-motion";
import { Textarea } from "../ui/textarea";
import { cn } from "@/lib/utils";

const cleanText = (text: string) => {
  return text.replaceAll("\\\n", "\n");
};

function ViewRawText({
  isRawView,
  setIsRawView,
}: {
  isRawView: boolean;
  setIsRawView: Dispatch<SetStateAction<boolean>>;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <TooltipIconButton
        tooltip={`View ${isRawView ? "rendered" : "raw"} markdown`}
        variant="outline"
        delayDuration={400}
        onClick={() => setIsRawView((p) => !p)}
      >
        {isRawView ? (
          <EyeOff className="w-5 h-5 text-gray-600" />
        ) : (
          <Eye className="w-5 h-5 text-gray-600" />
        )}
      </TooltipIconButton>
    </motion.div>
  );
}

export interface TextRendererProps {
  isEditing: boolean;
  isHovering: boolean;
  isInputVisible: boolean;
}

const TextRendererComponentInner = forwardRef<HTMLDivElement, TextRendererProps>((props, ref) => {
  // Memoize the editor configuration to prevent unnecessary recreations
  const editorConfig = useMemo(() => ({}), []);
  const editor = useCreateBlockNote(editorConfig);
  const { graphData } = useGraphContext();
  const {
    artifact,
    isStreaming,
    updateRenderedArtifactRequired,
    firstTokenReceived,
    setArtifact,
    setSelectedBlocks,
    setUpdateRenderedArtifactRequired,
  } = graphData;


  const [rawMarkdown, setRawMarkdown] = useState("");
  const [isRawView, setIsRawView] = useState(false);
  const [manuallyUpdatingArtifact, setManuallyUpdatingArtifact] =
    useState(false);
  // Track last rendered content and index to prevent infinite loops
  const lastRenderedContentRef = useRef<string>("");
  const lastRenderedIndexRef = useRef<number>(-1);
  const isUpdatingRef = useRef<boolean>(false);
  const pendingContentRef = useRef<string | null>(null);

  useEffect(() => {
    const selectedText = editor.getSelectedText();
    const selection = editor.getSelection();

    if (selectedText && selection) {
      if (!artifact) {
        console.error("Artifact not found");
        return;
      }

      const currentBlockIdx = artifact.currentIndex;
      const currentContent = artifact.contents.find(
        (c) => c.index === currentBlockIdx
      );
      if (!currentContent) {
        console.error("Current content not found");
        return;
      }
      if (!isArtifactMarkdownContent(currentContent)) {
        console.error("Current content is not markdown");
        return;
      }

      (async () => {
        const [markdownBlock, fullMarkdown] = await Promise.all([
          editor.blocksToMarkdownLossy(selection.blocks),
          editor.blocksToMarkdownLossy(editor.document),
        ]);
        setSelectedBlocks({
          fullMarkdown: cleanText(fullMarkdown),
          markdownBlock: cleanText(markdownBlock),
          selectedText: cleanText(selectedText),
        });
      })();
    }
  }, [editor.getSelectedText()]);

  useEffect(() => {
    if (!props.isInputVisible) {
      setSelectedBlocks(undefined);
    }
  }, [props.isInputVisible]);

  // Track artifact ID to detect when a different artifact is loaded
  const artifactIdRef = useRef<string | undefined>(undefined);
  
  useEffect(() => {
    if (!artifact) {
      console.log("[TextRenderer] No artifact");
      // Reset refs when artifact is cleared
      lastRenderedContentRef.current = "";
      lastRenderedIndexRef.current = -1;
      artifactIdRef.current = undefined;
      return;
    }
    
    // Generate a unique ID for this artifact based on its contents
    // This helps detect when we're loading a different artifact (e.g., from a different thread)
    const artifactId = JSON.stringify(artifact.contents.map(c => ({ index: c.index, type: c.type })));
    
    // If this is a different artifact, reset the refs to force update
    if (artifactIdRef.current !== artifactId) {
      lastRenderedContentRef.current = "";
      lastRenderedIndexRef.current = -1;
      artifactIdRef.current = artifactId;
      // Also reset updating flags when switching artifacts
      isUpdatingRef.current = false;
      pendingContentRef.current = null;
    }
    
    // If updateRenderedArtifactRequired is true, reset updating flags to allow update
    if (updateRenderedArtifactRequired && isUpdatingRef.current) {
      isUpdatingRef.current = false;
      pendingContentRef.current = null;
    }
    
    // Always update when artifact changes, even during streaming
    // Only skip if manually updating to avoid conflicts
    if (manuallyUpdatingArtifact) {
      return;
    }

    try {
      const currentIndex = artifact.currentIndex || 1;
      const currentContent = artifact.contents.find(
        (c) => c.index === currentIndex && c.type === "text"
      ) as ArtifactMarkdown | undefined;
      if (!currentContent) {
        console.log("[TextRenderer] No current content for index:", currentIndex, "contents:", artifact.contents.map(c => c.index));
        return;
      }

      const fullMarkdown = currentContent.fullMarkdown || "";
      
      // If updateRenderedArtifactRequired is true, force update even if content/index match
      // This handles cases where thread is switched and we need to refresh the display
      const shouldForceUpdate = updateRenderedArtifactRequired;
            
      // Skip if content and index haven't changed (unless forced update)
      if (!shouldForceUpdate && 
          lastRenderedContentRef.current === fullMarkdown && 
          lastRenderedIndexRef.current === currentIndex) {
        return;
      }
      
      // If already updating and it's the same content/index, skip
      if (isUpdatingRef.current) {
        // If we're trying to update to a different index, cancel current update and start new one
        if (lastRenderedIndexRef.current !== currentIndex || 
            (pendingContentRef.current && pendingContentRef.current !== fullMarkdown)) {
          isUpdatingRef.current = false;
          pendingContentRef.current = null;
        } else {
          return;
        }
      }
      
      // Mark as updating before starting async operation
      isUpdatingRef.current = true;
      pendingContentRef.current = null; // Clear any pending content
      
      const performUpdate = async (content: string, index: number) => {
        try {
          const markdownAsBlocks = await editor.tryParseMarkdownToBlocks(content);
          editor.replaceBlocks(editor.document, markdownAsBlocks);
          lastRenderedContentRef.current = content;
          lastRenderedIndexRef.current = index;
          setUpdateRenderedArtifactRequired(false);
          setManuallyUpdatingArtifact(false);
        } catch (parseError) {
          console.error("TextRenderer: Error parsing markdown:", parseError);
        } finally {
          // Clear the updating flag
          isUpdatingRef.current = false;
        }
      };
      
      performUpdate(fullMarkdown, currentIndex);
    } catch (e) {
      console.error("TextRenderer: Error updating:", e);
      isUpdatingRef.current = false;
      pendingContentRef.current = null;
    }
  }, [artifact, updateRenderedArtifactRequired, isStreaming]);

  useEffect(() => {
    if (isRawView) {
      (async () => {
        const markdown = await editor.blocksToMarkdownLossy(editor.document);
        setRawMarkdown(markdown);
      })();
    } else if (!isRawView && rawMarkdown) {
      try {
        (async () => {
          setManuallyUpdatingArtifact(true);
          const markdownAsBlocks =
            await editor.tryParseMarkdownToBlocks(rawMarkdown);
          editor.replaceBlocks(editor.document, markdownAsBlocks);
          setManuallyUpdatingArtifact(false);
        })();
      } catch (_) {
        setManuallyUpdatingArtifact(false);
      }
    }
  }, [isRawView, editor]);

  const isComposition = useRef(false);

  const onChange = async () => {
    if (
      isStreaming ||
      manuallyUpdatingArtifact ||
      updateRenderedArtifactRequired
    )
      return;

    const fullMarkdown = await editor.blocksToMarkdownLossy(editor.document);
    
    // Update lastRenderedContentRef before setArtifact to prevent useEffect from triggering replaceBlocks
    // This preserves cursor position when user is editing
    lastRenderedContentRef.current = fullMarkdown;
    
    setArtifact((prev) => {
      if (!prev) {
        return {
          currentIndex: 1,
          contents: [
            {
              index: 1,
              fullMarkdown: fullMarkdown,
              title: "Untitled",
              type: "text",
            },
          ],
        };
      } else {
        return {
          ...prev,
          contents: prev.contents.map((c) => {
            if (c.index === prev.currentIndex) {
              return {
                ...c,
                fullMarkdown: fullMarkdown,
              };
            }
            return c;
          }),
        };
      }
    });
  };

  const onChangeRawMarkdown = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newRawMarkdown = e.target.value;
    setRawMarkdown(newRawMarkdown);
    setArtifact((prev) => {
      if (!prev) {
        return {
          currentIndex: 1,
          contents: [
            {
              index: 1,
              fullMarkdown: newRawMarkdown,
              title: "Untitled",
              type: "text",
            },
          ],
        };
      } else {
        return {
          ...prev,
          contents: prev.contents.map((c) => {
            if (c.index === prev.currentIndex) {
              return {
                ...c,
                fullMarkdown: newRawMarkdown,
              };
            }
            return c;
          }),
        };
      }
    });
  };

  return (
    <div ref={ref} className="w-full h-full mt-2 flex flex-col border-t-[1px] border-gray-200 overflow-y-auto py-5 relative">
      {props.isHovering && artifact && (
        <div className="absolute flex gap-2 top-2 right-4 z-10">
          <CopyText currentArtifactContent={getArtifactContent(artifact)} />
          <ViewRawText isRawView={isRawView} setIsRawView={setIsRawView} />
        </div>
      )}
      {isRawView ? (
        <Textarea
          className="whitespace-pre-wrap font-mono text-sm px-[54px] border-0 shadow-none h-full outline-none ring-0 rounded-none  focus-visible:ring-0 focus-visible:ring-offset-0"
          value={rawMarkdown}
          onChange={onChangeRawMarkdown}
        />
      ) : (
        <>
          <style jsx global>{`
            .pulse-text .bn-block-group {
              animation: pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
            }

            @keyframes pulse {
              0%,
              100% {
                opacity: 1;
              }
              50% {
                opacity: 0.3;
              }
            }
          `}</style>
          <BlockNoteView
            key={artifact ? `blocknote-${JSON.stringify(artifact.contents.map(c => ({ index: c.index, type: c.type })))}` : 'blocknote-empty'}
            theme="light"
            formattingToolbar={false}
            slashMenu={false}
            onCompositionStartCapture={() => (isComposition.current = true)}
            onCompositionEndCapture={() => (isComposition.current = false)}
            onChange={onChange}
            editable={
              !isStreaming || props.isEditing || !manuallyUpdatingArtifact
            }
            editor={editor}
            className={cn(
              isStreaming && !firstTokenReceived ? "pulse-text" : "",
              "custom-blocknote-theme"
            )}
          >
            <SuggestionMenuController
              getItems={async () =>
                getDefaultReactSlashMenuItems(editor).filter(
                  (z) => z.group !== "Media"
                )
              }
              triggerCharacter={"/"}
            />
          </BlockNoteView>
        </>
      )}
    </div>
  );
});

TextRendererComponentInner.displayName = "TextRendererComponent";

export const TextRendererComponent = React.memo(TextRendererComponentInner);

export const TextRenderer = TextRendererComponent;
