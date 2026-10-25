// @vitest-environment jsdom

import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ResearchOptions } from "./ResearchOptions";

let root: Root;
let container: HTMLDivElement;
const files = [
  "active.md",
  "notes.md",
  "three.md",
  "four.md",
  "five.md",
  "six.md",
].map((path) => ({ path }));

function Harness({ disabled = false }: { disabled?: boolean }) {
  const [selected, setSelected] = useState(["active.md"]);
  return (
    <ResearchOptions
      files={files}
      selectedPaths={selected}
      onChange={setSelected}
      sourceCount={2}
      disabled={disabled}
    />
  );
}

beforeEach(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("research project material", () => {
  it("shows which files and registered sources will be used, and allows a web-only request", async () => {
    await act(async () => root.render(<Harness />));
    const inputs = [
      ...container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
    ];
    expect(
      inputs.filter((input) => input.checked).map((input) => input.value)
    ).toEqual(["active.md"]);
    expect(container.textContent).toContain("출처 2개");
    await act(async () => inputs[0].click());
    expect(inputs.every((input) => !input.checked)).toBe(true);
  });

  it("caps the selection at five files while allowing deselection", async () => {
    await act(async () => root.render(<Harness />));
    const inputs = [
      ...container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
    ];
    for (const input of inputs.slice(1, 5))
      await act(async () => input.click());
    expect(inputs[5].disabled).toBe(true);
    expect(inputs[0].disabled).toBe(false);
    await act(async () => inputs[0].click());
    expect(inputs[5].disabled).toBe(false);
  });

  it("disables all choices during submission", async () => {
    await act(async () => root.render(<Harness disabled />));
    expect(
      [...container.querySelectorAll("input")].every((input) => input.disabled)
    ).toBe(true);
  });
});
