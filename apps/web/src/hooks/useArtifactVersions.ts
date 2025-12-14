import { useMemo } from "react";
import { Artifact } from "@/shared/types";

export interface ArtifactVersionMetadata {
  versionIndices: number[];
  totalVersions: number;
  minIndex: number;
  maxIndex: number;
  latestIndex: number;
}

export interface VersionNavigation {
  previousIndex: number | null;
  nextIndex: number | null;
  isBackwardsDisabled: boolean;
  isForwardDisabled: boolean;
}

/**
 * Hook for managing artifact version metadata and navigation
 */
export function useArtifactVersions(artifact: Artifact | undefined) {
  const metadata = useMemo(() => {
    if (!artifact) {
      return null;
    }

    const versionMetadata = (artifact as any)._metadata;
    const versionIndices =
      versionMetadata?.version_indices || artifact.contents.map((c) => c.index);
    const sortedIndices = [...versionIndices].sort((a, b) => a - b);

    return {
      versionIndices: sortedIndices,
      totalVersions: versionMetadata?.total_versions || sortedIndices.length,
      minIndex: sortedIndices[0],
      maxIndex: sortedIndices[sortedIndices.length - 1],
      latestIndex: sortedIndices[sortedIndices.length - 1],
    } as ArtifactVersionMetadata;
  }, [artifact]);

  const getVersionNavigation = (
    currentIndex: number,
    isDiffMode: boolean = false
  ): VersionNavigation => {
    if (!metadata) {
      return {
        previousIndex: null,
        nextIndex: null,
        isBackwardsDisabled: true,
        isForwardDisabled: true,
      };
    }

    const currentPos = metadata.versionIndices.indexOf(currentIndex);
    // If currentIndex is not in the array, find the closest previous index
    let previousIndex: number | null = null;
    if (currentPos > 0) {
      previousIndex = metadata.versionIndices[currentPos - 1];
    } else if (currentPos === -1 && metadata.versionIndices.length > 0) {
      // Current index not in array, find the largest index that's less than currentIndex
      const sorted = [...metadata.versionIndices].sort((a, b) => b - a);
      previousIndex = sorted.find((idx) => idx < currentIndex) || null;
    }
    const nextIndex =
      currentPos >= 0 && currentPos < metadata.versionIndices.length - 1
        ? metadata.versionIndices[currentPos + 1]
        : null;

    // In diff mode, can't navigate to latest version (right side is always latest)
    const isForwardDisabled =
      metadata.totalVersions === 1 ||
      (isDiffMode && (nextIndex === null || nextIndex >= metadata.maxIndex)) ||
      (!isDiffMode && nextIndex === null);

    return {
      previousIndex,
      nextIndex,
      isBackwardsDisabled:
        metadata.totalVersions === 1 || previousIndex === null,
      isForwardDisabled,
    };
  };

  const getVersionContent = (index: number) => {
    if (!artifact) return null;
    return artifact.contents.find((c) => c.index === index) || null;
  };

  return {
    metadata,
    getVersionNavigation,
    getVersionContent,
  };
}
