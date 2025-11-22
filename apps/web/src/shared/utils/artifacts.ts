import {
  Artifact,
  ArtifactCode,
  ArtifactMarkdown,
} from "../types";

export const isArtifactCodeContent = (
  content: unknown
): content is ArtifactCode => {
  return !!(
    typeof content === "object" &&
    content &&
    "type" in content &&
    content.type === "code"
  );
};

export const isArtifactMarkdownContent = (
  content: unknown
): content is ArtifactMarkdown => {
  return !!(
    typeof content === "object" &&
    content &&
    "type" in content &&
    content.type === "text"
  );
};

export const getArtifactContent = (
  artifact: Artifact
): ArtifactCode | ArtifactMarkdown => {
  if (!artifact) {
    throw new Error("No artifact found.");
  }
  const currentContent = artifact.contents.find(
    (a) => a.index === artifact.currentIndex
  );
  if (!currentContent) {
    return artifact.contents[artifact.contents.length - 1];
  }
  return currentContent;
};

