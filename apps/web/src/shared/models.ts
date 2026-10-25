import { ModelConfigurationParams } from "./types";

// NOTE: Models are now fetched from the backend API at /api/models/list
// This file only exports model-related constants and types.
// The actual model list is dynamically loaded from the backend.

export const LANGCHAIN_USER_ONLY_MODELS: string[] = [];

// Models for which the backend omits sampling and fixes the temperature control.
export const TEMPERATURE_EXCLUDED_MODELS: string[] = [];

// Models which do NOT stream back tool calls.
export const NON_STREAMING_TOOL_CALLING_MODELS: string[] = [];

// Models which do NOT stream back text.
export const NON_STREAMING_TEXT_MODELS: string[] = [];

// Models which preform CoT before generating a final response.
export const THINKING_MODELS: string[] = [];

// These exports are now placeholders and will be replaced by data from the backend
export let ALL_MODELS: ModelConfigurationParams[] = [];
export type ALL_MODEL_NAMES = string;
export let DEFAULT_MODEL_NAME: string = "global.anthropic.claude-opus-5-5";
// A typed initial value lets existing canvas controls render while the server
// catalog loads. setModels replaces it with the configured backend default.
export let DEFAULT_MODEL_CONFIG: ModelConfigurationParams["config"] = {
  provider: "bedrock",
  temperatureRange: { min: 1, max: 1, default: 1, current: 1 },
  maxTokens: { min: 1, max: 128000, default: 4096, current: 4096 },
};

// Function to initialize models from backend
export function setModels(
  models: ModelConfigurationParams[],
  defaultName: string,
  defaultConfig: ModelConfigurationParams["config"],
) {
  ALL_MODELS = models;
  DEFAULT_MODEL_NAME = defaultName;
  DEFAULT_MODEL_CONFIG = defaultConfig;
  // The backend owns the model catalog. A fixed range means that sampling is
  // omitted for this model, including any configured geographic profile.
  TEMPERATURE_EXCLUDED_MODELS.splice(
    0,
    TEMPERATURE_EXCLUDED_MODELS.length,
    ...models
      .filter((model) => model.config.temperatureRange.min === model.config.temperatureRange.max)
      .map((model) => model.name),
  );
  THINKING_MODELS.splice(
    0,
    THINKING_MODELS.length,
    ...models
      .filter((model) => model.supportsReasoning)
      .map((model) => model.name),
  );
}

