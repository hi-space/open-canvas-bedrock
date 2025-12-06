import * as Icons from "lucide-react";
import {
  ALLOWED_VIDEO_TYPES,
  ALLOWED_AUDIO_TYPES,
  ALLOWED_IMAGE_TYPES,
  MAX_IMAGE_BASE64_SIZE,
  MAX_IMAGE_WIDTH,
  MAX_IMAGE_HEIGHT,
  IMAGE_QUALITY,
} from "@/constants";
import { useToast } from "@/hooks/use-toast";
import { ContextDocument } from "@/shared/types";
import { FFmpeg } from "@ffmpeg/ffmpeg";
import { toBlobURL } from "@ffmpeg/util";

export function arrayToFileList(files: File[] | undefined) {
  if (!files || !files.length) return undefined;
  const dt = new DataTransfer();
  files?.forEach((file) => dt.items.add(file));
  return dt.files;
}

export function contextDocumentToFile(document: ContextDocument): File {
  if (document.type === "text") {
    // For text documents, create file directly from the text data
    const blob = new Blob([document.data], { type: "text/plain" });
    return new File([blob], document.name, { type: "text/plain" });
  }

  // For non-text documents, handle as base64
  let base64String = document.data;
  if (base64String.includes(",")) {
    base64String = base64String.split(",")[1];
  }

  // Fix padding if necessary
  while (base64String.length % 4 !== 0) {
    base64String += "=";
  }

  // Clean the string (remove whitespace and invalid characters)
  base64String = base64String.replace(/\s/g, "");

  try {
    // Convert base64 to binary
    const binaryString = atob(base64String);

    // Convert binary string to Uint8Array
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    // Create Blob from the bytes
    const blob = new Blob([bytes], { type: document.type });

    // Create File object
    return new File([blob], document.name, { type: document.type });
  } catch (error) {
    console.error("Error converting data to file:", error);
    throw error;
  }
}

export async function transcribeAudio(file: File, userId: string) {
  // Supabase disabled - audio transcription not available
  throw new Error(
    "Audio transcription requires Supabase storage which is not configured."
  );
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(
          `Failed to convert file to base64. Received ${typeof reader.result} result.`
        );
      }
    };
    reader.onerror = (error) => reject(error);
  });
}

/**
 * Compress and resize image to reduce base64 size
 * Returns compressed image as base64 data URL
 */
export async function compressImage(
  file: File
): Promise<string> {
  return new Promise((resolve, reject) => {
    // Skip compression for SVG (vector graphics)
    if (file.type === "image/svg+xml") {
      fileToBase64(file).then(resolve).catch(reject);
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        // Calculate new dimensions while maintaining aspect ratio
        let width = img.width;
        let height = img.height;

        if (width > MAX_IMAGE_WIDTH || height > MAX_IMAGE_HEIGHT) {
          const ratio = Math.min(
            MAX_IMAGE_WIDTH / width,
            MAX_IMAGE_HEIGHT / height
          );
          width = Math.floor(width * ratio);
          height = Math.floor(height * ratio);
        }

        // Create canvas and draw resized image
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");

        if (!ctx) {
          reject(new Error("Failed to get canvas context"));
          return;
        }

        // Use high-quality image rendering
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(img, 0, 0, width, height);

        // Convert to blob with compression
        canvas.toBlob(
          (blob) => {
            if (!blob) {
              reject(new Error("Failed to compress image"));
              return;
            }

            // Check if compressed size is acceptable
            if (blob.size > MAX_IMAGE_BASE64_SIZE) {
              // If still too large, reduce quality and size further
              const reduceSize = () => {
                // Reduce dimensions by 25% more
                const newWidth = Math.floor(width * 0.75);
                const newHeight = Math.floor(height * 0.75);
                canvas.width = newWidth;
                canvas.height = newHeight;
                ctx.imageSmoothingEnabled = true;
                ctx.imageSmoothingQuality = "high";
                ctx.drawImage(img, 0, 0, newWidth, newHeight);
                
                canvas.toBlob(
                  (smallerBlob) => {
                    if (!smallerBlob) {
                      reject(new Error("Failed to compress image"));
                      return;
                    }
                    // Check size again, if still too large, reduce quality
                    if (smallerBlob.size > MAX_IMAGE_BASE64_SIZE) {
                      canvas.toBlob(
                        (finalBlob) => {
                          if (!finalBlob) {
                            reject(new Error("Failed to compress image"));
                            return;
                          }
                          const reader = new FileReader();
                          reader.onload = () => {
                            if (typeof reader.result === "string") {
                              resolve(reader.result);
                            } else {
                              reject(
                                `Failed to convert compressed image to base64. Received ${typeof reader.result} result.`
                              );
                            }
                          };
                          reader.onerror = reject;
                          reader.readAsDataURL(finalBlob);
                        },
                        file.type,
                        0.6 // Even lower quality
                      );
                    } else {
                      const reader = new FileReader();
                      reader.onload = () => {
                        if (typeof reader.result === "string") {
                          resolve(reader.result);
                        } else {
                          reject(
                            `Failed to convert compressed image to base64. Received ${typeof reader.result} result.`
                          );
                        }
                      };
                      reader.onerror = reject;
                      reader.readAsDataURL(smallerBlob);
                    }
                  },
                  file.type,
                  0.65 // Lower quality
                );
              };
              reduceSize();
            } else {
              const reader = new FileReader();
              reader.onload = () => {
                if (typeof reader.result === "string") {
                  resolve(reader.result);
                } else {
                  reject(
                    `Failed to convert compressed image to base64. Received ${typeof reader.result} result.`
                  );
                }
              };
              reader.onerror = reject;
              reader.readAsDataURL(blob);
            }
          },
          file.type,
          IMAGE_QUALITY
        );
      };
      img.onerror = () => {
        reject(new Error("Failed to load image"));
      };
      if (typeof e.target?.result === "string") {
        img.src = e.target.result;
      } else {
        reject(new Error("Failed to read image file"));
      }
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const MAX_AUDIO_SIZE = 26214400;

export async function load(
  ffmpeg: FFmpeg,
  messageRef: React.RefObject<HTMLDivElement>
) {
  // Check if FFmpeg is already loaded
  if (ffmpeg.loaded) {
    return;
  }

  const baseURL = "https://unpkg.com/@ffmpeg/core@0.12.10/dist/umd";
  ffmpeg.on("log", ({ message }) => {
    if (messageRef.current) messageRef.current.innerHTML = message;
  });
  // toBlobURL is used to bypass CORS issue, urls with the same
  // domain can be used directly.
  await ffmpeg.load({
    coreURL: await toBlobURL(`${baseURL}/ffmpeg-core.js`, "text/javascript"),
    wasmURL: await toBlobURL(`${baseURL}/ffmpeg-core.wasm`, "application/wasm"),
  });
}

export async function convertToAudio(
  videoFile: File,
  ffmpeg: FFmpeg
): Promise<File> {
  try {
    // Create a buffer from the video file
    const videoData = await videoFile.arrayBuffer();

    // Write the video buffer to FFmpeg's virtual filesystem
    await ffmpeg.writeFile("input.mp4", new Uint8Array(videoData));

    // Run FFmpeg command to convert video to audio
    await ffmpeg.exec([
      "-i",
      "input.mp4",
      "-vn",
      "-acodec",
      "libmp3lame",
      "-q:a",
      "2",
      "output.mp3",
    ]);

    // Read the output file from FFmpeg's virtual filesystem
    const audioData = await ffmpeg.readFile("output.mp3");

    // Create a Blob from the audio data
    // FFmpeg readFile returns Uint8Array, but TypeScript types may be incompatible
    // Create a new Uint8Array from the buffer to ensure compatibility
    const audioBytes = new Uint8Array(
      audioData instanceof Uint8Array ? audioData.buffer : (audioData as any)
    );
    const audioBlob = new Blob([audioBytes], { type: "audio/mp3" });

    // Generate a filename for the new audio file
    // You can customize this naming convention
    const originalName = videoFile.name;
    const audioFileName = originalName.replace(/\.[^/.]+$/, "") + ".mp3";

    // Create and return a new File object
    return new File([audioBlob], audioFileName, {
      type: "audio/mp3",
      lastModified: new Date().getTime(),
    });
  } catch (error) {
    console.error("Error converting video to audio:", error);
    throw error;
  }
}

export interface ConvertDocumentsProps {
  ffmpeg: FFmpeg;
  messageRef: React.RefObject<HTMLDivElement>;
  documents: FileList;
  userId: string;
  toast: ReturnType<typeof useToast>["toast"];
}

export async function convertDocuments({
  ffmpeg,
  messageRef,
  documents,
  userId,
  toast,
}: ConvertDocumentsProps): Promise<ContextDocument[]> {
  const files = Array.from(documents);
  const includesVideoFile = files.some((file) =>
    ALLOWED_VIDEO_TYPES.has(file.type)
  );
  if (includesVideoFile) {
    // Load FFmpeg
    await load(ffmpeg, messageRef);
  }

  const documentsPromise = Array.from(documents).map(async (doc) => {
    const isAudio = ALLOWED_AUDIO_TYPES.has(doc.type);
    const isVideo = ALLOWED_VIDEO_TYPES.has(doc.type);
    const isImage = ALLOWED_IMAGE_TYPES.has(doc.type);

    if (isAudio) {
      if (doc.size > MAX_AUDIO_SIZE) {
        toast({
          title: "Failed to transcribe audio",
          description: `Audio file "${doc.name}" is larger than the max size of 26214400 bytes. Received ${doc.size} bytes.`,
          variant: "destructive",
          duration: 7500,
        });
        return null;
      }

      toast({
        title: "Transcribing audio",
        description: (
          <span className="flex items-center gap-2">
            Transcribing audio {doc.name}. This may take a while. Please wait{" "}
            <Icons.LoaderCircle className="animate-spin w-4 h-4" />
          </span>
        ),
        duration: 15000,
      });

      const transcription = await transcribeAudio(doc, userId);

      toast({
        title: "Successfully transcribed audio",
        description: `Transcribed audio ${doc.name}.`,
      });

      return {
        name: doc.name,
        type: "text",
        data: transcription,
      };
    }

    if (isVideo) {
      toast({
        title: "Converting video to audio",
        description: (
          <span className="flex items-center gap-2">
            Converting video {doc.name} to audio. This may take a while. Please
            wait <Icons.LoaderCircle className="animate-spin w-4 h-4" />
          </span>
        ),
        duration: 15000,
      });

      // Convert video to audio
      const audioFile = await convertToAudio(doc, ffmpeg);

      if (audioFile.size > MAX_AUDIO_SIZE) {
        toast({
          title: "Failed to transcribe video",
          description: `Audio for video "${doc.name}" is larger than the max size of 26214400 bytes. Received ${audioFile.size} bytes.`,
          variant: "destructive",
          duration: 7500,
        });
        return null;
      }

      toast({
        title: "Successfully converted video to audio",
        description: (
          <span className="flex items-center gap-2">
            Video to audio conversion completed for {doc.name}. Transcribing
            audio now. This may take a while. Please wait{" "}
            <Icons.LoaderCircle className="animate-spin w-4 h-4" />
          </span>
        ),
        duration: 60000,
      });
      // Transcribe audio to video
      const transcription = await transcribeAudio(audioFile, userId);

      toast({
        title: "Successfully transcribed video",
        description: `Transcribed video ${doc.name}.`,
      });

      return {
        name: doc.name,
        type: "text",
        data: transcription,
      };
    }

    if (isImage) {
      // Compress and resize images to reduce base64 size
      try {
        const compressedBase64 = await compressImage(doc);
        // Double-check size after compression
        if (compressedBase64.length > MAX_IMAGE_BASE64_SIZE) {
          toast({
            title: "Image too large",
            description: `Image "${doc.name}" is too large even after compression. Please use a smaller image.`,
            variant: "destructive",
            duration: 5000,
          });
          return null;
        }
        return {
          name: doc.name,
          type: doc.type,
          data: compressedBase64,
        };
      } catch (error) {
        console.error("Error compressing image:", error);
        toast({
          title: "Failed to process image",
          description: `Failed to compress image "${doc.name}". Using original image.`,
          variant: "destructive",
          duration: 5000,
        });
        // Fallback to original
        return {
          name: doc.name,
          type: doc.type,
          data: await fileToBase64(doc),
        };
      }
    }

    return {
      name: doc.name,
      type: doc.type,
      data: await fileToBase64(doc),
    };
  });
  const documentsResult = (await Promise.all(documentsPromise)).filter(
    (x): x is ContextDocument => x !== null
  );
  return documentsResult;
}
