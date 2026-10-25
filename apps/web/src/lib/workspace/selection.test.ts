import { describe, expect, it } from "vitest";
import { mapRenderedSelection } from "./selection";

describe("rendered selection mapping", () => {
  it("maps a BOM-prefixed Windows document using exact source offsets", () => {
    const source = "\uFEFF# 제목\r\n\r\n원래 문장.";
    expect(
      mapRenderedSelection(
        source,
        { from: 9, to: 15, text: "원래 문장." },
        0,
        6
      )
    ).toEqual({ from: 9, to: 15, text: "원래 문장." });
  });

  it("maps ordinary text through its AST source position", () => {
    const text = "같은 문장. 같은 문장.";
    expect(
      mapRenderedSelection(text, { from: 0, to: text.length, text }, 7, 13)
    ).toEqual({
      from: 7,
      to: 13,
      text: "같은 문장.",
    });
  });

  it("maps the text inside bold styling without including its markers", () => {
    const source = "one **bold** and [link](https://example.org)";
    expect(
      mapRenderedSelection(
        source,
        { from: 0, to: source.length, text: "one bold and link" },
        4,
        8
      )
    ).toEqual({
      from: 6,
      to: 10,
      text: "bold",
    });
  });

  it("never maps formatted visible words onto a matching URL suffix", () => {
    const source = "foo [f**oo**](https://example.com/foo)";
    expect(
      mapRenderedSelection(
        source,
        { from: 0, to: source.length, text: "foo foo" },
        4,
        7
      )
    ).toBeUndefined();
  });

  it("declines selections spanning Markdown markers", () => {
    const source = "plain **bold** ending";
    expect(
      mapRenderedSelection(
        source,
        { from: 0, to: source.length, text: "plain bold ending" },
        0,
        10
      )
    ).toBeUndefined();
  });
});
