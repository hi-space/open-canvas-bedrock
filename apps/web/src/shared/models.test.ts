import { afterEach, describe, expect, it } from "vitest";
import {
  ALL_MODELS,
  DEFAULT_MODEL_CONFIG,
  DEFAULT_MODEL_NAME,
  TEMPERATURE_EXCLUDED_MODELS,
  THINKING_MODELS,
  setModels,
} from "./models";
import type { ModelConfigurationParams } from "./types";

const originalModels = ALL_MODELS;
const originalName = DEFAULT_MODEL_NAME;
const originalConfig = DEFAULT_MODEL_CONFIG;

afterEach(() => {
  setModels(originalModels, originalName, originalConfig);
});

describe("server-owned model capabilities", () => {
  it("recognizes reasoning models from catalog metadata across providers", () => {
    const models: ModelConfigurationParams[] = [
      {
        name: "global.openai.gpt-6.1-sol",
        label: "GPT-6.1 Sol",
        config: originalConfig,
        category: "OpenAI",
        isNew: true,
        supportsReasoning: true,
      },
      {
        name: "global.moonshotai.kimi-k3",
        label: "Kimi K3",
        config: originalConfig,
        category: "Moonshot AI",
        isNew: true,
        supportsReasoning: true,
      },
      {
        name: "example.text-model",
        label: "Text model",
        config: originalConfig,
        isNew: false,
      },
    ];

    setModels(models, models[0].name, models[0].config);

    expect(THINKING_MODELS).toEqual([
      "global.openai.gpt-6.1-sol",
      "global.moonshotai.kimi-k3",
    ]);
    expect(TEMPERATURE_EXCLUDED_MODELS).toContain("global.openai.gpt-6.1-sol");

    setModels([models[2]], models[2].name, models[2].config);
    expect(THINKING_MODELS).toEqual([]);
  });
});
