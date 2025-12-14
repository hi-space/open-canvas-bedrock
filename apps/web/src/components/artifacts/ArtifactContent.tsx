import React, { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { Artifact, ArtifactCode, ArtifactMarkdown } from "@/shared/types";
import { HumanMessage } from "@langchain/core/messages";
import { v4 as uuidv4 } from "uuid";
import { TextRenderer } from "./TextRenderer";
import { AskOpenCanvas } from "./components/AskOpenCanvas";
import { useGraphContext } from "@/contexts/GraphContext";
import { serializeLangChainMessage } from "@/lib/convert_messages";
import { getArtifactContent } from "@/shared/utils/artifacts";

export interface ArtifactContentProps {
  isEditing: boolean;
  isHovering: boolean;
  contentRef?: React.RefObject<HTMLDivElement>;
  artifactContentRef?: React.RefObject<HTMLDivElement>;
  highlightLayerRef?: React.RefObject<HTMLDivElement>;
  scrollContainerRef?: React.RefObject<HTMLDivElement>; // For diff mode scroll synchronization
  forceVersionIndex?: number; // Force display a specific version (for diff mode)
}

interface SelectionBox {
  top: number;
  left: number;
  text: string;
}

/**
 * Core artifact content rendering component.
 * Handles text selection, highlighting, and AskOpenCanvas functionality.
 * Can be reused in both normal mode and diff mode.
 */
export function ArtifactContent({
  isEditing,
  isHovering,
  contentRef: externalContentRef,
  artifactContentRef: externalArtifactContentRef,
  highlightLayerRef: externalHighlightLayerRef,
  scrollContainerRef,
  forceVersionIndex,
}: ArtifactContentProps) {
  const { graphData } = useGraphContext();
  const {
    artifact,
    selectedBlocks,
    setSelectedBlocks,
    setMessages,
    streamMessage,
  } = graphData;

  const internalContentRef = useRef<HTMLDivElement>(null);
  const internalArtifactContentRef = useRef<HTMLDivElement>(null);
  const internalHighlightLayerRef = useRef<HTMLDivElement>(null);
  const selectionBoxRef = useRef<HTMLDivElement>(null);

  const contentRef = externalContentRef || internalContentRef;
  const artifactContentRef = externalArtifactContentRef || internalArtifactContentRef;
  const highlightLayerRef = externalHighlightLayerRef || internalHighlightLayerRef;

  const [selectionBox, setSelectionBox] = useState<SelectionBox>();
  const [selectionIndexes, setSelectionIndexes] = useState<{
    start: number;
    end: number;
  }>();
  const [isInputVisible, setIsInputVisible] = useState(false);
  const [isSelectionActive, setIsSelectionActive] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [isValidSelectionOrigin, setIsValidSelectionOrigin] = useState(false);

  const handleMouseUp = useCallback(() => {
    const selection = window.getSelection();
    if (selection && selection.rangeCount > 0 && contentRef.current) {
      const range = selection.getRangeAt(0);
      const selectedText = range.toString().trim();

      if (selectedText && artifactContentRef.current) {
        const isWithinArtifact = (node: Node | null): boolean => {
          if (!node) return false;
          if (node === artifactContentRef.current) return true;
          return isWithinArtifact(node.parentNode);
        };

        const startInArtifact = isWithinArtifact(range.startContainer);
        const endInArtifact = isWithinArtifact(range.endContainer);

        if (startInArtifact && endInArtifact) {
          setIsValidSelectionOrigin(true);
          const rects = range.getClientRects();
          const firstRect = rects[0];
          const lastRect = rects[rects.length - 1];
          const contentRect = contentRef.current.getBoundingClientRect();

          const boxWidth = 400;
          let left = lastRect.right - contentRect.left - boxWidth;

          if (left < 0) {
            left = Math.min(0, firstRect.left - contentRect.left);
          }
          if (left < 0) {
            left = Math.min(0, firstRect.left - contentRect.left);
          }

          const newSelectionBox = {
            top: lastRect.bottom - contentRect.top,
            left: left,
            text: selectedText,
          };
          setSelectionBox(newSelectionBox);
          setIsInputVisible(false);
          setIsSelectionActive(true);
        } else {
          setIsValidSelectionOrigin(false);
          handleCleanupState();
        }
      }
    }
  }, [contentRef, artifactContentRef]);

  const handleCleanupState = () => {
    setIsInputVisible(false);
    setSelectionBox(undefined);
    setSelectionIndexes(undefined);
    setIsSelectionActive(false);
    setIsValidSelectionOrigin(false);
    setInputValue("");
  };

  const handleDocumentMouseDown = useCallback(
    (event: MouseEvent) => {
      if (
        isSelectionActive &&
        selectionBoxRef.current &&
        !selectionBoxRef.current.contains(event.target as Node)
      ) {
        handleCleanupState();
      }
    },
    [isSelectionActive]
  );

  const handleSelectionBoxMouseDown = useCallback((event: React.MouseEvent) => {
    event.stopPropagation();
  }, []);

  const handleSubmit = async (content: string) => {
    const humanMessage = new HumanMessage({
      content,
      id: uuidv4(),
      additional_kwargs: selectedBlocks
        ? {
            highlightedText: selectedBlocks,
          }
        : {},
    });

    setMessages((prevMessages) => [...prevMessages, humanMessage]);
    handleCleanupState();
    await streamMessage({
      messages: [serializeLangChainMessage(humanMessage)],
    });
  };

  useEffect(() => {
    document.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("mousedown", handleDocumentMouseDown);

    return () => {
      document.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("mousedown", handleDocumentMouseDown);
    };
  }, [handleMouseUp, handleDocumentMouseDown]);

  useEffect(() => {
    try {
      if (artifactContentRef.current && highlightLayerRef.current) {
        const content = artifactContentRef.current;
        const highlightLayer = highlightLayerRef.current;

        highlightLayer.innerHTML = "";

        if (isSelectionActive && selectionBox) {
          const selection = window.getSelection();
          if (selection && selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);

            if (content.contains(range.commonAncestorContainer)) {
              const rects = range.getClientRects();
              const layerRect = highlightLayer.getBoundingClientRect();

              for (let i = 0; i < rects.length; i++) {
                const rect = rects[i];
                const highlightEl = document.createElement("div");
                highlightEl.className =
                  "absolute bg-[#3597934d] pointer-events-none";

                const verticalPadding = 3;
                highlightEl.style.left = `${rect.left - layerRect.left}px`;
                highlightEl.style.top = `${rect.top - layerRect.top - verticalPadding}px`;
                highlightEl.style.width = `${rect.width}px`;
                highlightEl.style.height = `${rect.height + verticalPadding * 2}px`;

                highlightLayer.appendChild(highlightEl);
              }
            }
          }
        }
      }
    } catch (e) {
      console.error("Failed to get artifact selection", e);
    }
  }, [isSelectionActive, selectionBox, artifactContentRef, highlightLayerRef]);

  useEffect(() => {
    if (!!selectedBlocks && !isSelectionActive) {
      setSelectedBlocks(undefined);
    }
  }, [selectedBlocks, isSelectionActive, setSelectedBlocks]);

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      const activeElement = document.activeElement;
      const isInputActive =
        activeElement instanceof HTMLInputElement ||
        activeElement instanceof HTMLTextAreaElement;

      if (
        (isInputVisible || selectionBox || isSelectionActive) &&
        !isInputActive
      ) {
        if (e.key.length === 1 || e.key === "Backspace" || e.key === "Delete") {
          handleCleanupState();
        }
      }

      if ((isInputVisible || isSelectionActive) && e.key === "Escape") {
        handleCleanupState();
      }
    };

    document.addEventListener("keydown", handleKeyPress);
    return () => document.removeEventListener("keydown", handleKeyPress);
  }, [isInputVisible, selectionBox, isSelectionActive]);

  if (!artifact) {
    return null;
  }

  // If forceVersionIndex is provided, use that version; otherwise use currentIndex
  const currentArtifactContent = forceVersionIndex !== undefined
    ? artifact.contents.find((c) => c.index === forceVersionIndex) || getArtifactContent(artifact)
    : getArtifactContent(artifact);

  return (
    <div
      ref={scrollContainerRef || contentRef}
      className={cn("flex justify-center h-full overflow-auto")}
    >
      <div className={cn("relative min-h-full min-w-full")}>
        <div
          className="h-full"
          ref={artifactContentRef}
        >
          {currentArtifactContent.type === "text" ? (
            <TextRenderer
              isInputVisible={isInputVisible}
              isEditing={isEditing}
              isHovering={isHovering}
            />
          ) : null}
        </div>
        <div
          ref={highlightLayerRef}
          className="absolute top-0 left-0 w-full h-full pointer-events-none"
        />
      </div>
      {selectionBox && isSelectionActive && isValidSelectionOrigin && (
        <AskOpenCanvas
          ref={selectionBoxRef}
          inputValue={inputValue}
          setInputValue={setInputValue}
          isInputVisible={isInputVisible}
          selectionBox={selectionBox}
          setIsInputVisible={setIsInputVisible}
          handleSubmitMessage={handleSubmit}
          handleSelectionBoxMouseDown={handleSelectionBoxMouseDown}
          artifact={artifact}
          selectionIndexes={selectionIndexes}
          handleCleanupState={handleCleanupState}
        />
      )}
    </div>
  );
}

