import { describe, expect, it } from "vitest";
import {
  extractReferences,
  insertCitation,
  referenceUrl,
  validateProposalReferences,
} from "./sources";

describe("reference links", () => {
  it("finds citations in HTML without counting links inside scripts or comments", () => {
    const html = `<html><head><style>a {color: green}</style></head><body>
      <section><a href="https://example.org/source" title="자료">[1]</a>
      <a href="https://example.org/source">[1]</a></section>
      <!-- <a href="https://example.org/comment">ignored</a> -->
      <script>const link = '<a href="https://example.org/script">ignored</a>';</script>
      </body></html>`;
    const links = extractReferences(html);
    expect(links).toHaveLength(1);
    expect(links[0]).toMatchObject({
      url: "https://example.org/source",
      title: "자료",
      count: 2,
    });
  });

  it("accepts real web links and rejects executable or credential-bearing URLs", () => {
    expect(referenceUrl(" https://example.org/a?x=1#part ")).toBe(
      "https://example.org/a?x=1#part"
    );
    for (const url of [
      "javascript:alert(1)",
      "data:text/html,x",
      "file:///etc/passwd",
      "https://user:pass@example.org",
    ]) {
      expect(referenceUrl(url)).toBeNull();
    }
  });

  it("finds inline, reference-style, and footnote sources without treating code as links", () => {
    const markdown = [
      "내용 [1](https://example.org/a_(b)). 다른 [글][article]. 각주[^1]",
      '[article]: https://example.org/b "자료 제목"',
      "[^1]: 근거 [원문](https://example.org/c)",
      "",
      "```md",
      "[fake](https://example.org/not-a-source)",
      "```",
    ].join("\n");
    expect(extractReferences(markdown).map((source) => source.url)).toEqual([
      "https://example.org/a_(b)",
      "https://example.org/b",
      "https://example.org/c",
    ]);
  });

  it("deduplicates repeated citations while keeping their reference label", () => {
    const references = extractReferences(
      "하나 [7](https://example.org/a). 둘 [7](https://example.org/a)."
    );
    expect(references).toHaveLength(1);
    expect(references[0].label).toBe("7");
    expect(references[0].count).toBe(2);
  });

  it("inserts at the requested sentence and uses the existing citation number", () => {
    const source = {
      id: "s",
      title: '원문 "제목"',
      url: "https://example.org/a_(b)",
    };
    const content =
      "첫 문장. 다음 문장.\n\n기존 [3](https://example.org/a_(b)).";
    const result = insertCitation(content, source, 5);
    expect(result).toBe(
      '첫 문장. [3](<https://example.org/a_(b)> "원문 \\"제목\\"") 다음 문장.\n\n기존 [3](https://example.org/a_(b)).'
    );
    expect(extractReferences(result).map((reference) => reference.url)).toEqual(
      ["https://example.org/a_(b)"]
    );
  });

  it("rejects unsafe references before modifying a document", () => {
    expect(() =>
      insertCitation(
        "본문",
        { id: "x", title: "x", url: "javascript:alert(1)" },
        2
      )
    ).toThrow();
  });

  it("rejects an invented destination after a partial URL selection is reassembled", () => {
    expect(() =>
      validateProposalReferences(
        "근거 [1](https://example.org/original)",
        "근거 [1](https://invented.org/original)",
        []
      )
    ).toThrow(/출처/);
  });

  it("allows a new citation only when a supplied reference includes evidence", () => {
    const after = "근거 [1](https://example.org/source)";
    const source = {
      id: "s",
      title: "원문",
      url: "https://example.org/source",
    };
    expect(() => validateProposalReferences("", after, [source])).toThrow(
      /출처/
    );
    expect(() =>
      validateProposalReferences("", after, [
        { ...source, excerpt: "원문 발췌" },
      ])
    ).not.toThrow();
  });

  it("does not allow an AI rewrite to drop existing citations", () => {
    expect(() =>
      validateProposalReferences(
        "근거 [1](https://example.org/source)",
        "출처 없는 근거",
        []
      )
    ).toThrow(/출처/);
  });

  it("uses stable bounded identifiers for long article URLs", () => {
    const url = `https://example.org/article/${"a".repeat(300)}`;
    const source = extractReferences(`[1](${url})`)[0];
    expect(source.id.length).toBeLessThanOrEqual(100);
    expect(extractReferences(`[1](${url})`)[0].id).toBe(source.id);
    expect(extractReferences(`[1](${url}b)`)[0].id).not.toBe(source.id);
  });
});
