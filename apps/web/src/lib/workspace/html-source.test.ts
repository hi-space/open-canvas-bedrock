import { describe, expect, it } from "vitest";
import { parse, parseFragment } from "parse5";
import { insertHtmlCitation } from "./html-source";
import { extractReferences } from "./sources";

const source = {
  id: "reference-1",
  title: '근거 <문서> "원문"',
  url: "https://example.org/source?a=1&b=2",
  excerpt: "출처의 발췌",
};

describe("HTML source references", () => {
  it("places a citation outside a clickable card when its paragraph is selected", () => {
    const result = insertHtmlCitation(
      '<a href="#target" data-oc-id="card"><p data-oc-id="p">클릭할 카드</p></a>',
      source,
      "p"
    );
    expect(result).toMatch(/클릭할 카드<\/p><\/a><p><a /);
    expect(result).toContain('data-source-ids="[&quot;reference-1&quot;]"');
  });

  it.each([
    '<strong data-oc-id="inline">굵은 내용</strong>',
    '<a data-oc-id="inline" href="https://example.org/old">원문</a>',
    '<img data-oc-id="inline" alt="그림">',
  ])(
    "keeps a citation for an inline selection in its existing paragraph: %s",
    (inline) => {
      const result = insertHtmlCitation(
        `<p>앞 ${inline} 뒤</p>`,
        source,
        "inline"
      );
      const nodes = parseFragment(result).childNodes.filter(
        (node) => "tagName" in node
      );
      expect(nodes).toHaveLength(1);
      expect(nodes[0]).toMatchObject({ tagName: "p" });
      expect(result).toMatch(/<\/a> 뒤<\/p>$/);
    }
  );

  it("preserves a slash in an unquoted final attribute when inserting provenance", () => {
    const result = insertHtmlCitation(
      '<p data-oc-id="p" class=foo/>내용</p>',
      source,
      "p"
    );
    const paragraph = parseFragment(result).childNodes[0];
    expect(paragraph).toMatchObject({
      tagName: "p",
      attrs: expect.arrayContaining([{ name: "class", value: "foo/" }]),
    });
  });

  it("adds provenance and an escaped citation only to the selected duplicate paragraph", () => {
    const before =
      '<main data-oc-id="main"><p data-oc-id="one">같은 글 🙂</p><p data-oc-id="two">같은 글 🙂</p></main>';
    const result = insertHtmlCitation(before, source, "two");
    expect(result).toContain('<p data-oc-id="one">같은 글 🙂</p>');
    expect(result).toContain('data-source-ids="[&quot;reference-1&quot;]"');
    expect(result).toContain("근거 &lt;문서&gt; &quot;원문&quot;");
    expect(result).toContain('href="https://example.org/source?a=1&amp;b=2"');
    expect(result).toMatch(/같은 글 🙂 <a[^>]+>.*<\/a><\/p><\/main>$/);
    expect(extractReferences(result).map((item) => item.url)).toEqual([
      source.url,
    ]);
  });

  it("places a table row citation after the table rather than inside its structure", () => {
    const before =
      '<main><table><tbody><tr data-oc-id="row"><td>내용</td></tr></tbody></table></main>';
    const result = insertHtmlCitation(before, source, "row");
    expect(result).toContain("</tbody></table><p>");
    expect(result).toContain('data-oc-id="row" data-source-ids=');
    expect(parse(result)).toBeDefined();
  });

  it("inserts a document citation before the closing body tag", () => {
    const result = insertHtmlCitation(
      "<!doctype html><html><head><title>자료</title></head><body><p>본문</p></body></html>",
      source
    );
    expect(result).toMatch(/<\/a><\/p><\/body><\/html>$/);
  });

  it("rejects a missing region or unsafe reference", () => {
    expect(() => insertHtmlCitation("<p>본문</p>", source, "gone")).toThrow(
      /선택/
    );
    expect(() =>
      insertHtmlCitation("<p>본문</p>", {
        ...source,
        url: "javascript:alert(1)",
      })
    ).toThrow(/출처/);
  });
});
