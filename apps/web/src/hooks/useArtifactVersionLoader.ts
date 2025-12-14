import { useEffect, useState, useCallback, useRef } from "react";
import { Artifact } from "@/shared/types";
import { API_URL } from "@/constants";
import { useThreadContext } from "@/contexts/ThreadProvider";

interface UseArtifactVersionLoaderOptions {
  /**
   * Whether to preserve currentIndex when loading versions (for diff mode)
   */
  preserveCurrentIndex?: boolean;
}

/**
 * Hook for loading artifact versions without changing the current selection
 * Useful for diff mode where we need to load base versions without affecting the latest version display
 */
export function useArtifactVersionLoader(
  artifact: Artifact | undefined,
  setArtifact: React.Dispatch<React.SetStateAction<Artifact | undefined>>,
  options: UseArtifactVersionLoaderOptions = {}
) {
  const { threadId } = useThreadContext();
  const [loadingVersions, setLoadingVersions] = useState<Set<number>>(
    new Set()
  );
  const loadingRef = useRef<Set<number>>(new Set());

  const loadVersion = useCallback(
    async (versionIndex: number) => {
      if (!threadId || !artifact) {
        return false;
      }

      // Check if version already exists in artifact
      const existingContent = artifact.contents.find(
        (c) => c.index === versionIndex
      );
      if (existingContent) {
        return true;
      }

      // Check if already loading (using ref for synchronous check)
      if (loadingRef.current.has(versionIndex)) {
        return false;
      }

      // Mark as loading
      loadingRef.current.add(versionIndex);
      setLoadingVersions(new Set(loadingRef.current));

      try {
        const response = await fetch(
          `${API_URL}/api/threads/${threadId}/artifact?version=${versionIndex}`
        );

        if (!response.ok) {
          throw new Error(`Failed to load version ${versionIndex}`);
        }

        const versionArtifact = await response.json();
        const newContent = versionArtifact.contents?.[0];

        if (newContent) {
          setArtifact((prev) => {
            if (!prev) return prev;

            // Check if this version already exists (might have been loaded by another request)
            const existingIndex = prev.contents.findIndex(
              (c: any) => c.index === versionIndex
            );
            let updatedContents;

            if (existingIndex >= 0) {
              // Replace existing version
              updatedContents = [...prev.contents];
              updatedContents[existingIndex] = newContent;
            } else {
              // Add new version
              updatedContents = [...prev.contents, newContent];
            }

            return {
              ...prev,
              contents: updatedContents,
              // Preserve currentIndex if requested (for diff mode)
              currentIndex: options.preserveCurrentIndex
                ? prev.currentIndex
                : prev.currentIndex,
            };
          });

          return true;
        }
      } catch (error) {
        console.error(`Failed to load artifact version ${versionIndex}:`, error);
      } finally {
        // Remove from loading set
        loadingRef.current.delete(versionIndex);
        setLoadingVersions(new Set(loadingRef.current));
      }

      return false;
    },
    [threadId, artifact, setArtifact, options.preserveCurrentIndex]
  );

  const isVersionLoading = useCallback(
    (versionIndex: number) => {
      return loadingVersions.has(versionIndex);
    },
    [loadingVersions]
  );

  const isVersionLoaded = useCallback(
    (versionIndex: number) => {
      if (!artifact) return false;
      return artifact.contents.some((c) => c.index === versionIndex);
    },
    [artifact]
  );

  // Reset loading state when artifact changes significantly
  useEffect(() => {
    loadingRef.current.clear();
    setLoadingVersions(new Set());
  }, [artifact?.contents.length, threadId]);

  return {
    loadVersion,
    isVersionLoading,
    isVersionLoaded,
  };
}
