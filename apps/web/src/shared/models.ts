import { ModelConfigurationParams } from "./types";

// NOTE: Models are now fetched from the backend API at /api/models/list
// This file only exports model-related constants and types.
// The actual model list is dynamically loaded from the backend.

export const LANGCHAIN_USER_ONLY_MODELS: string[] = [];

// Models which do NOT support the temperature parameter.
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
export let DEFAULT_MODEL_NAME: string = "";
export let DEFAULT_MODEL_CONFIG: any = null;

// Function to initialize models from backend
export function setModels(models: ModelConfigurationParams[], defaultName: string, defaultConfig: any) {
  ALL_MODELS = models;
  DEFAULT_MODEL_NAME = defaultName;
  DEFAULT_MODEL_CONFIG = defaultConfig;
}

