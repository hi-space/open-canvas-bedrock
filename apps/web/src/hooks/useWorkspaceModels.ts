"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_MODEL_NAME } from "@/shared/models";

export function useWorkspaceModels() {
  const [model, setModel] = useState(DEFAULT_MODEL_NAME);
  const [models, setModels] = useState([
    { name: DEFAULT_MODEL_NAME, label: "Claude Opus 5.5" },
  ]);
  const [unavailable, setUnavailable] = useState(false);
  const current = useRef<AbortController | undefined>(undefined);
  const load = useCallback(async () => {
    current.current?.abort();
    const controller = new AbortController();
    current.current = controller;
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch("/api/models/list", {
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Model catalog unavailable");
      const data = (await response.json()) as {
        models?: { name: string; label: string }[];
        defaultModelName?: string;
      };
      const catalog = data.models?.filter(
        (item) =>
          typeof item.name === "string" && typeof item.label === "string"
      );
      if (!catalog?.length) throw new Error("Empty model catalog");
      if (current.current !== controller) return;
      setModels(catalog);
      setModel((previous) =>
        catalog.some((item) => item.name === previous)
          ? previous
          : (catalog.find((item) => item.name === data.defaultModelName)
              ?.name ?? catalog[0].name)
      );
      setUnavailable(false);
    } catch {
      if (current.current === controller) setUnavailable(true);
    } finally {
      clearTimeout(timer);
    }
  }, []);
  useEffect(() => {
    void load();
    return () => current.current?.abort();
  }, [load]);
  return { model, models, setModel, unavailable, load };
}
