export const API_URL =
  process.env.API_URL ?? process.env.FASTAPI_API_URL ?? "http://localhost:9000";
// v2 is tied to the 'open-canvas-prod' deployment.
export const ASSISTANT_ID_COOKIE = "oc_assistant_id_v2";
// export const ASSISTANT_ID_COOKIE = "oc_assistant_id";
export const HAS_ASSISTANT_COOKIE_BEEN_SET = "has_oc_assistant_id_been_set";

export const OC_HAS_SEEN_CUSTOM_ASSISTANTS_ALERT =
  "oc_has_seen_custom_assistants_alert";
export const WEB_SEARCH_RESULTS_QUERY_PARAM = "webSearchResults";

export const ALLOWED_AUDIO_TYPES = new Set([
  "audio/mp3",
  "audio/mp4",
  "audio/mpeg",
  "audio/mpga",
  "audio/m4a",
  "audio/wav",
  "audio/webm",
]);
export const ALLOWED_AUDIO_TYPE_ENDINGS = [
  ".mp3",
  ".mpga",
  ".m4a",
  ".wav",
  ".webm",
];
export const ALLOWED_VIDEO_TYPES = new Set([
  "video/mp4",
  "video/mpeg",
  "video/webm",
]);
export const ALLOWED_VIDEO_TYPE_ENDINGS = [".mp4", ".mpeg", ".webm"];

export const ALLOWED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/gif",
  "image/webp",
  "image/svg+xml",
]);

// Maximum base64 size for images (2MB) to avoid model input length limits
// Base64 encoding increases size by ~33%, so this allows ~1.5MB original image
// Reduced to prevent "Input is too long" errors and improve efficiency
export const MAX_IMAGE_BASE64_SIZE = 2 * 1024 * 1024; // 2MB
// Maximum dimensions for images to reduce size
// Reduced from 2048 to further compress images
export const MAX_IMAGE_WIDTH = 1536;
export const MAX_IMAGE_HEIGHT = 1536;
// Lower quality for better compression
export const IMAGE_QUALITY = 0.75; // JPEG quality (0-1) - reduced from 0.85

export const CHAT_COLLAPSED_QUERY_PARAM = "chatCollapsed";
