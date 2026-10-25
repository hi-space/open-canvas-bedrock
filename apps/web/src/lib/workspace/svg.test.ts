// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import {
  createHtmlPreview,
  htmlRegions,
  selectionForHtmlMessage,
} from "./html";

const svg =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 160" data-oc-id="diagram" role="img" aria-label="요청 흐름"><title>API 요청</title><g stroke="#246a56"><rect data-oc-id="shape" x="10" y="20" width="120" height="80"/><path d="M 130 60 L 300 60"/></g><text x="25" y="65">API 요청</text></svg>';

describe("native SVG regions and preview", () => {
  it("maps the whole SVG, never individual geometry, and preserves UTF-16 source offsets", () => {
    const content =
      '<p data-oc-id="before">앞 😀</p>' + svg + '<p data-oc-id="after">뒤</p>';
    const regions = htmlRegions(content);
    expect(regions.map((region) => region.nodeId)).toEqual([
      "before",
      "diagram",
      "after",
    ]);
    const region = regions[1];
    expect(region.text).toBe(svg);
    expect(region.from).toBe(content.indexOf("<svg"));
    expect(content.slice(region.from, region.to)).toBe(svg);
    expect(
      selectionForHtmlMessage(
        { type: "oc-html-select", token: "test", nodeId: "diagram" },
        "test",
        content
      )?.text
    ).toBe(svg);
    expect(
      selectionForHtmlMessage(
        { type: "oc-html-select", token: "test", nodeId: "shape" },
        "test",
        content
      )
    ).toBeUndefined();
  });

  it("preserves safe SVG geometry in the SVG namespace and strips child editor IDs", () => {
    const preview = new DOMParser().parseFromString(
      createHtmlPreview(svg, "token", false),
      "text/html"
    );
    const diagram = preview.querySelector("svg")!;
    expect(diagram).not.toBeNull();
    expect(diagram.namespaceURI).toBe("http://www.w3.org/2000/svg");
    expect(diagram.getAttribute("viewBox")).toBe("0 0 480 160");
    expect(diagram.querySelector("path")?.getAttribute("d")).toBe(
      "M 130 60 L 300 60"
    );
    expect(diagram.querySelector("text")?.textContent).toBe("API 요청");
    expect(diagram.querySelector("[data-oc-id]")).toBeNull();
    expect(preview.querySelector("script")).toBeNull();
  });

  it("allows selecting an explicitly self-closed SVG root", () => {
    const content = '<svg viewBox="0 0 100 100" data-oc-id="empty"/>';
    expect(htmlRegions(content)[0]?.text).toBe(content);
  });

  it("removes nested SVG viewports just as the save validator rejects them", () => {
    const content =
      '<svg data-oc-id="outer"><g><svg><text>Nested</text></svg></g><text>Outer</text></svg>';
    const preview = new DOMParser().parseFromString(
      createHtmlPreview(content, "token", false),
      "text/html"
    );
    expect(preview.querySelector("svg svg")).toBeNull();
    expect(preview.querySelector("svg")?.textContent).toBe("Outer");
  });

  it("removes active SVG and HTML integration descendants without enabling resources", () => {
    const unsafe =
      '<svg data-oc-id="diagram" viewBox="0 0 100 100" onload="bad()"><script>bad()</script><foreignObject><iframe src="https://evil.test"></iframe></foreignObject><desc><p onclick="bad()">HTML</p></desc><use href="#x"/><image href="https://evil.test/p.png"/><animate attributeName="x"/><rect fill="url(https://evil.test/paint)" style="stroke:u\\72l(https://evil.test/paint)"/><text>Safe</text></svg>';
    const preview = new DOMParser().parseFromString(
      createHtmlPreview(unsafe, "token", false),
      "text/html"
    );
    expect(
      preview.querySelector(
        "foreignObject,iframe,svg script,use,image,animate,svg p"
      )
    ).toBeNull();
    expect(preview.querySelector("svg")?.hasAttribute("onload")).toBe(false);
    expect(preview.querySelector("rect")?.hasAttribute("fill")).toBe(false);
    expect(preview.querySelector("rect")?.hasAttribute("style")).toBe(false);
    expect(preview.querySelector("text")?.textContent).toBe("Safe");
  });
});
