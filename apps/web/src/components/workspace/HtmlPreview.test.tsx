// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HtmlPreview } from "./HtmlPreview";
import type { TextSelection } from "../../lib/workspace/types";

const content =
  '<section data-oc-id="section"><p data-oc-id="p">Text</p></section>';
const paragraph: TextSelection = {
  from: 30,
  to: 56,
  text: '<p data-oc-id="p">Text</p>',
  nodeId: "p",
};
let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (
    globalThis as typeof globalThis & {
      IS_REACT_ACT_ENVIRONMENT: boolean;
    }
  ).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe("HTML preview controls", () => {
  it("isolates the document and offers a labeled native region picker", async () => {
    await act(async () => {
      root.render(
        <HtmlPreview
          content={content}
          title="기획서 HTML 미리보기"
          onSelection={() => undefined}
        />
      );
    });
    const frame = container.querySelector("iframe");
    expect(frame?.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame?.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(frame?.title).toBe("기획서 HTML 미리보기");
    const picker = container.querySelector("select");
    expect(picker).not.toBeNull();
    expect(
      container.querySelector(`label[for="${picker!.id}"]`)?.textContent
    ).toBe("영역 선택");
    expect([...picker!.options].map((option) => option.value)).toEqual([
      "",
      "section",
      "p",
    ]);
  });

  it("selects the exact chosen region through the keyboard-accessible picker", async () => {
    const onSelection = vi.fn();
    await act(async () => {
      root.render(<HtmlPreview content={content} onSelection={onSelection} />);
    });
    const picker = container.querySelector("select")!;
    await act(async () => {
      picker.value = "p";
      picker.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(onSelection).toHaveBeenLastCalledWith(
      expect.objectContaining(paragraph)
    );
  });

  it("exposes parent selection and an explicit clear action", async () => {
    const onSelection = vi.fn();
    await act(async () => {
      root.render(
        <HtmlPreview
          content={content}
          selection={paragraph}
          onSelection={onSelection}
        />
      );
    });
    const parent = container.querySelector<HTMLButtonElement>(
      'button[aria-label="상위 영역 선택"]'
    );
    expect(parent?.disabled).toBe(false);
    await act(async () => parent!.click());
    expect(onSelection).toHaveBeenLastCalledWith(
      expect.objectContaining({
        nodeId: "section",
        from: 0,
        text: content,
      })
    );
    await act(async () =>
      container
        .querySelector<HTMLButtonElement>('button[aria-label="선택 해제"]')!
        .click()
    );
    expect(onSelection).toHaveBeenLastCalledWith(undefined);
  });

  it("keeps the loaded frame stable when selection changes", async () => {
    const onSelection = vi.fn();
    await act(async () =>
      root.render(<HtmlPreview content={content} onSelection={onSelection} />)
    );
    const frame = container.querySelector("iframe")!;
    const initialSource = frame.srcdoc;
    await act(async () =>
      root.render(
        <HtmlPreview
          content={content}
          selection={paragraph}
          onSelection={onSelection}
        />
      )
    );
    expect(container.querySelector("iframe")).toBe(frame);
    expect(frame.srcdoc).toBe(initialSource);
    expect(container.querySelector("select")?.value).toBe("p");
  });

  it("renders compact comparisons without selection controls or scripts", async () => {
    await act(async () =>
      root.render(
        <HtmlPreview content={content} onSelection={() => undefined} compact />
      )
    );
    expect(container.querySelector("select, button")).toBeNull();
    const frame = container.querySelector("iframe")!;
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(
      new DOMParser()
        .parseFromString(frame.srcdoc, "text/html")
        .querySelector("script")
    ).toBeNull();
  });

  it("accepts only messages from the current frame and preview session", async () => {
    const onSelection = vi.fn();
    await act(async () =>
      root.render(<HtmlPreview content={content} onSelection={onSelection} />)
    );
    const frame = container.querySelector("iframe")!;
    const frameWindow = frame.contentWindow!;
    const outgoing: { type: string; token: string }[] = [];
    frameWindow.addEventListener("message", (event) =>
      outgoing.push(event.data)
    );
    await act(async () => frame.dispatchEvent(new Event("load")));
    await vi.waitFor(() => expect(outgoing.length).toBeGreaterThan(0));
    const token = outgoing[0].token;
    const emit = (source: Window, sessionToken: string) =>
      window.dispatchEvent(
        new MessageEvent("message", {
          source,
          data: {
            type: "oc-html-select",
            token: sessionToken,
            nodeId: "p",
            from: 999,
            text: "Forged text",
          },
        })
      );
    await act(async () => {
      emit(window, token);
      emit(frameWindow, "obsolete");
    });
    expect(onSelection).not.toHaveBeenCalled();
    await act(async () => emit(frameWindow, token));
    expect(onSelection).toHaveBeenLastCalledWith(
      expect.objectContaining(paragraph)
    );

    onSelection.mockClear();
    await act(async () =>
      root.render(
        <HtmlPreview
          content={content.replace("Text", "Changed")}
          onSelection={onSelection}
        />
      )
    );
    await act(async () => emit(frameWindow, token));
    expect(onSelection).not.toHaveBeenCalled();
  });
});
