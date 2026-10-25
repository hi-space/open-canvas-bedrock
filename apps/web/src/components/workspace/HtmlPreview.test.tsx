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
  vi.unstubAllGlobals();
});

describe("HTML preview controls", () => {
  it("reports an unreadable PNG instead of silently showing a broken image", async () => {
    const header = Uint8Array.from([
      137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1,
      0, 0, 0, 1,
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(header, {
            headers: { "Content-Type": "image/png" },
          })
      )
    );
    await act(async () =>
      root.render(
        <HtmlPreview
          content={
            content + '<img src="/api/research/assets/run/fig1.png" alt="그림">'
          }
        />
      )
    );
    expect(container.textContent).toMatch(/그림.*불러오지/);
    expect(container.querySelector("iframe")?.srcdoc).toContain("Text");
  });
  it("shows readable text and a retry action when a research image is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 404 }))
    );
    await act(async () =>
      root.render(
        <HtmlPreview
          content={
            content + '<img src="/api/research/assets/run/fig1.png" alt="그림">'
          }
        />
      )
    );
    expect(container.querySelector("iframe")?.srcdoc).toContain("Text");
    expect(container.textContent).toMatch(/그림.*불러오지/);
    expect(
      [...container.querySelectorAll("button")].some((button) =>
        button.textContent?.includes("다시 불러오기")
      )
    ).toBe(true);
  });

  it("does not replace a newer document with an obsolete image result", async () => {
    let finish!: (response: Response) => void;
    const oldRequest = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(() => oldRequest)
    );
    await act(async () =>
      root.render(
        <HtmlPreview
          content={
            content + '<img src="/api/research/assets/run/fig1.png" alt="그림">'
          }
        />
      )
    );
    await act(async () =>
      root.render(<HtmlPreview content='<p data-oc-id="new">새 문서</p>' />)
    );
    await act(async () => {
      finish(new Response("", { status: 404 }));
      await oldRequest;
    });
    expect(container.querySelector("iframe")?.srcdoc).toContain("새 문서");
    expect(container.querySelector("iframe")?.srcdoc).not.toContain("Text");
    expect(container.textContent).not.toMatch(/그림.*불러오지/);
  });
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
