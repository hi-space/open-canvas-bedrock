import { CustomModelConfig, ModelConfigurationParams } from "./types";

const BEDROCK_MODELS: ModelConfigurationParams[] = [
  {
    name: "bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0",
    label: "Claude Haiku 4.5",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Anthropic",
  },
  {
    name: "bedrock/global.anthropic.claude-sonnet-4-20250514-v1:0",
    label: "Claude Sonnet 4",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Anthropic",
  },
  {
    name: "bedrock/global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    label: "Claude Sonnet 4.5",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Anthropic",
  },
  {
    name: "bedrock/us.anthropic.claude-opus-4-1-20250805-v1:0",
    label: "Claude Opus 4.1",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Anthropic",
  },
  {
    name: "bedrock/us.amazon.nova-premier-v1:0",
    label: "Nova Premier",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Amazon",
  },
  {
    name: "bedrock/us.amazon.nova-pro-v1:0",
    label: "Nova Pro",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Amazon",
  },
  {
    name: "bedrock/us.amazon.nova-micro-v1:0",
    label: "Nova Micro",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Amazon",
  },
  {
    name: "bedrock/us.amazon.nova-lite-v1:0",
    label: "Nova Lite",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Amazon",
  },
  {
    name: "bedrock/us.meta.llama3-3-70b-instruct-v1:0",
    label: "Llama 3.3 70B Instruct",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "Meta",
  },
  {
    name: "bedrock/us.deepseek.r1-v1:0",
    label: "DeepSeek R1",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "DeepSeek",
  },
  {
    name: "bedrock/deepseek.v3-v1:0",
    label: "DeepSeek V3",
    config: {
      provider: "bedrock",
      temperatureRange: {
        min: 0,
        max: 1,
        default: 0.5,
        current: 0.5,
      },
      maxTokens: {
        min: 1,
        max: 8_192,
        default: 4_096,
        current: 4_096,
      },
    },
    isNew: false,
    category: "DeepSeek",
  },
];

export const LANGCHAIN_USER_ONLY_MODELS: string[] = [];

// Models which do NOT support the temperature parameter.
export const TEMPERATURE_EXCLUDED_MODELS: string[] = [];

// Models which do NOT stream back tool calls.
export const NON_STREAMING_TOOL_CALLING_MODELS: string[] = [];

// Models which do NOT stream back text.
export const NON_STREAMING_TEXT_MODELS: string[] = [];

// Models which preform CoT before generating a final response.
export const THINKING_MODELS: string[] = [];

export const ALL_MODELS: ModelConfigurationParams[] = [
  ...BEDROCK_MODELS,
];

type BEDROCK_MODEL_NAMES = (typeof BEDROCK_MODELS)[number]["name"];
export type ALL_MODEL_NAMES = BEDROCK_MODEL_NAMES;

export const DEFAULT_MODEL_NAME: ALL_MODEL_NAMES = BEDROCK_MODELS[0].name;
export const DEFAULT_MODEL_CONFIG: CustomModelConfig = {
  ...BEDROCK_MODELS[0].config,
  temperatureRange: { ...BEDROCK_MODELS[0].config.temperatureRange },
  maxTokens: { ...BEDROCK_MODELS[0].config.maxTokens },
};

