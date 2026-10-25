// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveHtmlResearchImages, standaloneHtml } from "./html-assets";

const url = "/api/research/assets/run123/fig1.png";
const png = Uint8Array.from(
  atob(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
  ),
  (character) => character.charCodeAt(0)
);
const response = () =>
  new Response(png.slice(), { headers: { "Content-Type": "image/png" } });
const source = `<section data-oc-id="s"><p>자료 <a href="https://example.org/source">[1]</a></p><img data-oc-id="image" src="${url}" alt="흐름"></section>`;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("research images in HTML", () => {
  it("embeds an authenticated managed PNG while keeping citations and element identities", async () => {
    const fetcher = vi.fn(async () => response());
    vi.stubGlobal("fetch", fetcher);
    const result = await resolveHtmlResearchImages(source);
    expect(result.missing).toEqual([]);
    const parsed = new DOMParser().parseFromString(result.content, "text/html");
    expect(parsed.querySelector("img")?.getAttribute("src")).toMatch(
      /^data:image\/png;base64,/
    );
    expect(parsed.querySelector("img")?.getAttribute("data-oc-id")).toBe(
      "image"
    );
    expect(parsed.querySelector("a")?.getAttribute("href")).toBe(
      "https://example.org/source"
    );
    expect(source).toContain(`src="${url}"`);
    expect(fetcher).toHaveBeenCalledWith(
      url,
      expect.objectContaining({
        credentials: "same-origin",
        redirect: "error",
        signal: expect.any(AbortSignal),
      })
    );
  });

  it("loads repeated image references once and never requests arbitrary URLs", async () => {
    const fetcher = vi.fn(async () => response());
    vi.stubGlobal("fetch", fetcher);
    const input =
      source +
      `<img src='${url}'><img src="https://outside.example/image.png">` +
      '<img src="/api/research/assets/../secret.png"><img src="//other/api/research/assets/r/f.png">';
    const result = await resolveHtmlResearchImages(input);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(result.content.match(/data:image\/png;base64,/g)).toHaveLength(2);
    expect(result.content).toContain('src="https://outside.example/image.png"');
  });

  it.each([
    () => new Response("missing", { status: 404 }),
    () =>
      new Response("<svg></svg>", {
        headers: { "Content-Type": "image/svg+xml" },
      }),
    () =>
      new Response("<html>sign in</html>", {
        headers: { "Content-Type": "image/png" },
      }),
    () =>
      new Response(new Uint8Array(2 * 1024 * 1024 + 1), {
        headers: { "Content-Type": "image/png" },
      }),
  ])(
    "keeps readable content when an asset is unavailable or invalid",
    async (makeResponse) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => makeResponse())
      );
      const result = await resolveHtmlResearchImages(source);
      expect(result.missing).toEqual([url]);
      expect(result.content).toBe(source);
      await expect(standaloneHtml(source)).rejects.toThrow(/그림/);
    }
  );

  it("rejects a redirected image even if a fetch adapter followed it", async () => {
    const redirected = response();
    Object.defineProperty(redirected, "redirected", { value: true });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => redirected)
    );
    expect((await resolveHtmlResearchImages(source)).missing).toEqual([url]);
  });

  it("exports a self-contained image and preserves the source link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response())
    );
    const exported = await standaloneHtml(source);
    expect(exported).not.toContain(url);
    expect(exported).toContain("data:image/png;base64,");
    expect(exported).toContain('href="https://example.org/source"');
  });

  it("leaves excess images unresolved when the document exceeds twelve distinct assets", async () => {
    const fetcher = vi.fn(async () => response());
    vi.stubGlobal("fetch", fetcher);
    const input = Array.from(
      { length: 13 },
      (_, index) => `<img src="/api/research/assets/run123/fig${index}.png">`
    ).join("");
    const result = await resolveHtmlResearchImages(input);
    expect(result.missing).toEqual(["/api/research/assets/run123/fig12.png"]);
    expect(result.content.match(/data:image\/png;base64,/g)).toHaveLength(12);
    expect(fetcher).toHaveBeenCalledTimes(12);
  });

  it("stops at the shared eight-MiB budget even when each image is individually valid", async () => {
    const bytes = new Uint8Array(2 * 1024 * 1024);
    bytes.set(png);
    const fetcher = vi.fn(
      async () =>
        new Response(bytes.slice(), {
          headers: { "Content-Type": "image/png" },
        })
    );
    vi.stubGlobal("fetch", fetcher);
    const input = Array.from(
      { length: 5 },
      (_, index) => `<img src="/api/research/assets/run123/large${index}.png">`
    ).join("");
    const result = await resolveHtmlResearchImages(input);
    expect(result.missing).toEqual(["/api/research/assets/run123/large4.png"]);
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it("stops loading an obsolete document when the caller aborts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, options: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            options.signal?.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError"))
            );
          })
      )
    );
    const controller = new AbortController();
    const loading = resolveHtmlResearchImages(source, controller.signal);
    controller.abort();
    await expect(loading).rejects.toMatchObject({ name: "AbortError" });
  });

  it("returns an image notice after the bounded loading timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url, options: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            options.signal?.addEventListener("abort", () =>
              reject(new DOMException("Timed out", "AbortError"))
            );
          })
      )
    );
    const loading = resolveHtmlResearchImages(source);
    await vi.advanceTimersByTimeAsync(15000);
    expect((await loading).missing).toEqual([url]);
  });
});
