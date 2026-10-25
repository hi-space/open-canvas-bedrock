// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createHtmlPreview,
  htmlRegions,
  selectionForHtmlMessage,
} from "./html";

describe("HTML source regions", () => {
  it("maps repeated text after emoji to exact UTF-16 source ranges", () => {
    const content =
      '😀\r\n<p data-oc-id="first">같은 문장</p>\r\n<p data-oc-id="second">같은 문장</p>';
    expect(htmlRegions(content)).toMatchObject([
      {
        nodeId: "first",
        from: 4,
        to: 35,
        text: '<p data-oc-id="first">같은 문장</p>',
        previewText: "같은 문장",
      },
      {
        nodeId: "second",
        from: 37,
        to: 69,
        text: '<p data-oc-id="second">같은 문장</p>',
        previewText: "같은 문장",
      },
    ]);
  });

  it("keeps exact quoted attributes, decoded labels, and source reference IDs", () => {
    const content = `<section data-oc-id='section' aria-label="Facts &amp; figures"><p data-oc-id="evidence" data-source-ids='["ref-1","ref-2","ref-1"]'>A &amp; B</p></section>`;
    const regions = htmlRegions(content);
    expect(regions[0]).toMatchObject({
      nodeId: "section",
      label: "section · Facts & figures",
      sourceIds: [],
    });
    expect(regions[1]).toMatchObject({
      nodeId: "evidence",
      parentId: "section",
      previewText: "A & B",
      sourceIds: ["ref-1", "ref-2"],
      text: `<p data-oc-id="evidence" data-source-ids='["ref-1","ref-2","ref-1"]'>A &amp; B</p>`,
    });
  });

  it("does not infer IDs or select head, active, or inert content", () => {
    const content = `<!doctype html><html data-oc-id="html"><head data-oc-id="head"><style data-oc-id="style">p{color:red}</style><title data-oc-id="title">Title</title></head><body data-oc-id="body"><div>Plain</div><script data-oc-id="script">bad()</script><template data-oc-id="template"><p data-oc-id="in-template">Hidden</p></template><svg data-oc-id="svg"><text data-oc-id="svg-text">SVG</text></svg><p data-oc-id="allowed">Content</p></body></html>`;
    expect(htmlRegions(content).map((region) => region.nodeId)).toEqual([
      "allowed",
    ]);
  });

  it("does not expose custom or unsupported elements as editable regions", () => {
    expect(
      htmlRegions(
        '<custom-card data-oc-id="custom">Card</custom-card><meter data-oc-id="meter">20%</meter><p data-oc-id="supported">Text</p>'
      ).map((region) => region.nodeId)
    ).toEqual(["supported"]);
  });

  it("rejects duplicate IDs, duplicate attributes, and invalid IDs", () => {
    const content = `<p data-oc-id="duplicate">A</p><p data-oc-id="duplicate">B</p><p data-oc-id="one" data-oc-id="two">C</p><p data-oc-id="bad id">D</p><p data-oc-id="valid_id-2">E</p>`;
    expect(htmlRegions(content).map((region) => region.nodeId)).toEqual([
      "valid_id-2",
    ]);
  });

  it("requires explicit complete non-void elements and keeps void source spans", () => {
    const content = `<p data-oc-id="unclosed">First<p data-oc-id="complete">Second</p><img data-oc-id="image" alt="Chart">`;
    expect(htmlRegions(content)).toMatchObject([
      {
        nodeId: "complete",
        text: '<p data-oc-id="complete">Second</p>',
      },
      {
        nodeId: "image",
        text: '<img data-oc-id="image" alt="Chart">',
        previewText: "Chart",
      },
    ]);
  });

  it("does not expose a containing range that includes foster-parented content", () => {
    const content = `<table data-oc-id="table"><p data-oc-id="moved">Moved</p><tr><td data-oc-id="cell">Cell</td></tr></table>`;
    expect(htmlRegions(content).map((region) => region.nodeId)).toEqual([
      "moved",
      "cell",
    ]);
    expect(htmlRegions(content)[1].parentId).toBeUndefined();
  });

  it.each(["&nbsp;", "\u00a0", "\u2003", "text"])(
    "excludes a table whose source text is rendered outside it: %j",
    (text) => {
      const content = `<section data-oc-id="section"><table data-oc-id="table">${text}<tr><td data-oc-id="cell">Cell</td></tr></table></section>`;
      const regions = htmlRegions(content);
      expect(regions.map((region) => region.nodeId)).toEqual([
        "section",
        "cell",
      ]);
      expect(regions[1].parentId).toBe("section");
    }
  );

  it("excludes a table when foster-parented text merges with preceding text", () => {
    const content = `Before<table data-oc-id="table">&nbsp;<tr><td data-oc-id="cell">Cell</td></tr></table>`;
    expect(htmlRegions(content).map((region) => region.nodeId)).toEqual([
      "cell",
    ]);
  });

  it("keeps valid table regions containing HTML ASCII whitespace", () => {
    const content = `<table data-oc-id="table"> \t\r\n\f<tr><td data-oc-id="cell">Cell</td></tr>\n</table>`;
    expect(htmlRegions(content)).toMatchObject([
      { nodeId: "table", text: content },
      {
        nodeId: "cell",
        parentId: "table",
        text: '<td data-oc-id="cell">Cell</td>',
      },
    ]);
  });

  it("does not expose a paragraph auto-closed by a summary element", () => {
    const content = `<p data-oc-id="paragraph">Before<summary data-oc-id="summary">Summary</summary></p>`;
    expect(htmlRegions(content).map((region) => region.nodeId)).toEqual([
      "summary",
    ]);
  });

  it("ignores malformed source reference metadata", () => {
    const content = `<p data-oc-id="a" data-source-ids="ref-1,ref-2">A</p><p data-oc-id="b" data-source-ids='["ref-1",42]'>B</p><p data-oc-id="c" data-source-ids='{"id":"ref-1"}'>C</p>`;
    expect(htmlRegions(content).map((region) => region.sourceIds)).toEqual([
      [],
      [],
      [],
    ]);
  });
});

describe("HTML selection message validation", () => {
  const content = '<p data-oc-id="paragraph">Exact <b>source</b></p>';

  it("resolves IDs against the source instead of trusting frame offsets or text", () => {
    const selection = selectionForHtmlMessage(
      {
        type: "oc-html-select",
        token: "session",
        nodeId: "paragraph",
        from: 500,
        to: 900,
        text: "Forged",
        sourceIds: ["forged-reference"],
      },
      "session",
      content
    );
    expect(selection).toMatchObject({
      from: 0,
      to: 49,
      text: content,
      nodeId: "paragraph",
      previewText: "Exact source",
      sourceIds: [],
    });
  });

  it.each([
    null,
    "oc-html-select",
    { type: "oc-html-select", token: "obsolete", nodeId: "paragraph" },
    { type: "other", token: "session", nodeId: "paragraph" },
    { type: "oc-html-select", token: "session", nodeId: "missing" },
    { type: "oc-html-select", token: "session", nodeId: ["paragraph"] },
  ])("rejects invalid or stale messages: %j", (message) => {
    expect(
      selectionForHtmlMessage(message, "session", content)
    ).toBeUndefined();
  });

  it("does not select a removed or ambiguous node in the current source", () => {
    const message = {
      type: "oc-html-select",
      token: "session",
      nodeId: "paragraph",
    };
    expect(
      selectionForHtmlMessage(message, "session", "<p>Changed</p>")
    ).toBeUndefined();
    expect(
      selectionForHtmlMessage(message, "session", content + content)
    ).toBeUndefined();
  });
});

function previewDocument(
  content: string,
  interactive = true,
  token = "preview-session"
): Document {
  return new DOMParser().parseFromString(
    createHtmlPreview(content, token, interactive),
    "text/html"
  );
}

describe("isolated HTML preview", () => {
  it("preserves the document head and inline CSS with safe static HTML", () => {
    const preview = previewDocument(
      '<!doctype html><html lang="ko"><head><title>기획서</title><style>.card { color: #345c44; }</style></head><body><main data-oc-id="card" class="card" style="padding:24px"><h1 data-oc-id="title">제목</h1></main></body></html>'
    );
    expect(preview.title).toBe("기획서");
    expect(preview.documentElement.lang).toBe("ko");
    expect(preview.head.querySelector("style")?.textContent).toContain(
      ".card { color: #345c44; }"
    );
    expect(preview.querySelector("main")?.getAttribute("style")).toContain(
      "padding:24px"
    );
    expect(preview.querySelector("h1")?.textContent).toBe("제목");
  });

  it("removes active markup, embedded contexts, event handlers, and refreshes", () => {
    const preview = previewDocument(`
      <head>
        <base href="https://evil.test/">
        <meta http-equiv="refresh" content="0; url=https://evil.test/">
        <link rel="stylesheet" href="https://evil.test/style.css">
        <script>window.generatedScriptRan = true</script>
      </head>
      <body onload="alert(1)">
        <p data-oc-id="safe" onclick="alert(1)">Safe</p>
        <iframe srcdoc="<script>alert(1)</script>"></iframe>
        <object data="https://evil.test/plugin"></object>
        <embed src="https://evil.test/embed">
        <form action="https://evil.test/"><input autofocus><button>Submit</button></form>
        <template><img src=x onerror=alert(1)></template>
        <svg><a href="https://evil.test"><text>SVG link</text></a></svg>
      </body>`);
    expect(
      preview.querySelector(
        "base,link,iframe,object,embed,form,input,button,template,svg"
      )
    ).toBeNull();
    expect(preview.querySelector('meta[http-equiv="refresh"]')).toBeNull();
    expect(
      [...preview.querySelectorAll("*")].flatMap((element) =>
        [...element.attributes]
          .filter((attribute) => attribute.name.startsWith("on"))
          .map((attribute) => attribute.name)
      )
    ).toEqual([]);
    const scripts = preview.querySelectorAll("script");
    expect(scripts).toHaveLength(1);
    expect(scripts[0].textContent).not.toContain("generatedScriptRan");
    expect(preview.querySelector("p")?.textContent).toBe("Safe");
  });

  it("places a deny-by-default CSP before content and permits only its bridge nonce", () => {
    const preview = previewDocument(
      '<style>@import "https://evil.test/style.css"; body { background: url(https://evil.test/pixel); }</style><p data-oc-id="p">Text</p>'
    );
    const policy = preview.head.firstElementChild;
    expect(policy?.tagName).toBe("META");
    expect(policy?.getAttribute("http-equiv")).toBe("Content-Security-Policy");
    const directives = new Map(
      (policy?.getAttribute("content") ?? "")
        .split(";")
        .map((part) => part.trim().split(/\s+/))
        .filter(([name]) => name)
        .map(([name, ...values]) => [name, values])
    );
    expect(directives.get("default-src")).toEqual(["'none'"]);
    for (const name of [
      "connect-src",
      "frame-src",
      "object-src",
      "form-action",
      "base-uri",
      "font-src",
    ])
      expect(directives.get(name)).toEqual(["'none'"]);
    expect(directives.get("style-src")).toEqual(["'unsafe-inline'"]);
    expect(directives.get("img-src")).toEqual(["data:"]);
    const nonce = preview.querySelector("script")?.getAttribute("nonce");
    expect(nonce).toMatch(/^[a-zA-Z0-9_-]{20,}$/);
    expect(directives.get("script-src")).toEqual([`'nonce-${nonce}'`]);
    expect(directives.get("script-src-attr")).toEqual(["'none'"]);
  });

  it("moves early root styles after the CSP without allowing raw-text breakout", () => {
    const preview = previewDocument(
      `<html style='color: green; background: url(https://evil.test/root); --label: "</style><meta http-equiv=refresh content=0>";'><head style="background:url(https://evil.test/head)"></head><body><p data-oc-id="p" style="color:blue">Safe</p></body></html>`
    );
    expect(preview.documentElement.hasAttribute("style")).toBe(false);
    expect(preview.head.hasAttribute("style")).toBe(false);
    expect(preview.querySelector('meta[http-equiv="refresh"]')).toBeNull();
    expect(preview.head.firstElementChild?.tagName).toBe("META");
    expect(preview.head.querySelector("style")?.textContent).toContain(
      "color: green"
    );
    expect(preview.head.querySelector("style")?.textContent).toContain(
      "\\3c /style>"
    );
    expect(preview.querySelector("p")?.getAttribute("style")).toBe(
      "color:blue"
    );
  });

  it.each([true, false])(
    "prevents navigation and external resource destinations (interactive=%s)",
    (interactive) => {
      const preview = previewDocument(
        `<a data-oc-id="link" href="https://evil.test" target="_self" ping="https://evil.test/ping">Link</a><a href="#local">Jump</a><a href="javascript:alert(1)">JS</a><img data-oc-id="image" src="https://evil.test/image.png" srcset="//evil.test/2x 2x"><img src="data:image/png;base64,aGVsbG8="><div background="https://evil.test/bg" style="color:green">Text</div>`,
        interactive
      );
      expect(
        preview.querySelector(
          "[href],[target],[ping],[srcset],[background],[action],[formaction]"
        )
      ).toBeNull();
      expect(
        preview.querySelector('img[data-oc-id="image"]')?.hasAttribute("src")
      ).toBe(false);
      expect(preview.querySelector("img[src]")?.getAttribute("src")).toBe(
        "data:image/png;base64,aGVsbG8="
      );
      expect(preview.querySelector("a")?.textContent).toBe("Link");
    }
  );

  it("does not add selection scripts in a read-only comparison", () => {
    const preview = previewDocument(
      '<p data-oc-id="paragraph">Read only</p>',
      false
    );
    expect(preview.querySelector("script")).toBeNull();
    expect(preview.head.firstElementChild?.getAttribute("content")).toContain(
      "script-src 'none'"
    );
  });

  it("removes ambiguous IDs and forged preview instrumentation", () => {
    const preview = previewDocument(
      '<p data-oc-id="dup">A</p><p data-oc-id="dup">B</p><p data-oc-id="valid" data-oc-preview-selected="true" nonce="forged">C</p>'
    );
    expect(
      [...preview.querySelectorAll("[data-oc-id]")].map((element) =>
        element.getAttribute("data-oc-id")
      )
    ).toEqual(["valid"]);
    expect(preview.querySelector("[data-oc-preview-selected]")).toBeNull();
    expect(preview.querySelector("p[nonce]")).toBeNull();
  });

  it("escapes an arbitrary session token without permitting script breakout", () => {
    const preview = previewDocument(
      '<p data-oc-id="p">Safe</p>',
      true,
      '</script><script id="breakout">alert(1)</script>'
    );
    expect(preview.querySelectorAll("script")).toHaveLength(1);
    expect(preview.querySelector("#breakout")).toBeNull();
    expect(preview.querySelector("p")?.textContent).toBe("Safe");
  });
});

function livePreview(content: string): HTMLIFrameElement {
  const frame = document.createElement("iframe");
  frame.dataset.htmlTest = "true";
  document.body.append(frame);
  const frameDocument = frame.contentDocument!;
  frameDocument.open();
  frameDocument.write(createHtmlPreview(content, "live-session", true));
  frameDocument.close();
  return frame;
}

afterEach(() => {
  for (const frame of document.querySelectorAll("iframe[data-html-test]"))
    frame.remove();
});

describe("trusted preview bridge", () => {
  it("reports only the closest eligible element ID and session token", async () => {
    const received: unknown[] = [];
    const receive = (event: MessageEvent) => received.push(event.data);
    window.addEventListener("message", receive);
    try {
      const frame = livePreview(
        '<section data-oc-id="section"><p data-oc-id="paragraph"><strong data-oc-id="bold">Repeated text</strong></p></section>'
      );
      const click = new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
      });
      frame.contentDocument!.querySelector("strong")!.dispatchEvent(click);
      await vi.waitFor(() => {
        expect(received).toContainEqual({
          type: "oc-html-select",
          token: "live-session",
          nodeId: "bold",
        });
      });
      expect(click.defaultPrevented).toBe(true);
    } finally {
      window.removeEventListener("message", receive);
    }
  });

  it("synchronizes selection and clear from the parent while rejecting stale messages", () => {
    const frame = livePreview(
      '<main data-oc-id="root" style="outline:1px dotted red !important"><p data-oc-id="child">Text</p></main>'
    );
    const frameWindow = frame.contentWindow!;
    const root = frame.contentDocument!.querySelector("main")!;
    const highlight = (token: string, nodeId: string | null) =>
      frameWindow.dispatchEvent(
        new MessageEvent("message", {
          source: frameWindow.parent,
          data: { type: "oc-html-highlight", token, nodeId },
        })
      );

    highlight("obsolete", "root");
    expect(root.hasAttribute("data-oc-preview-selected")).toBe(false);
    highlight("live-session", "root");
    expect(root.hasAttribute("data-oc-preview-selected")).toBe(true);
    expect(root.style.getPropertyValue("outline-offset")).toBe("-3px");
    expect(root.style.getPropertyPriority("outline")).toBe("important");
    expect(root.style.getPropertyValue("outline")).not.toBe("1px dotted red");
    highlight("obsolete", null);
    expect(root.hasAttribute("data-oc-preview-selected")).toBe(true);
    highlight("live-session", null);
    expect(root.hasAttribute("data-oc-preview-selected")).toBe(false);
    expect(root.style.getPropertyValue("outline")).toBe("1px dotted red");
    expect(root.style.getPropertyPriority("outline")).toBe("important");
  });

  it("ignores highlight messages that do not come from its parent", () => {
    const frame = livePreview('<p data-oc-id="p">Text</p>');
    frame.contentWindow!.dispatchEvent(
      new MessageEvent("message", {
        source: frame.contentWindow,
        data: {
          type: "oc-html-highlight",
          token: "live-session",
          nodeId: "p",
        },
      })
    );
    expect(
      frame.contentDocument!.querySelector("[data-oc-preview-selected]")
    ).toBeNull();
  });

  it("shows a hover outline without changing the selected source region", () => {
    const frame = livePreview('<p data-oc-id="p"><span>Hover here</span></p>');
    frame
      .contentDocument!.querySelector("span")!
      .dispatchEvent(new MouseEvent("pointerover", { bubbles: true }));
    expect(
      frame
        .contentDocument!.querySelector("p")
        ?.hasAttribute("data-oc-preview-hover")
    ).toBe(true);
    expect(
      frame.contentDocument!.querySelector("[data-oc-preview-selected]")
    ).toBeNull();
  });
});
