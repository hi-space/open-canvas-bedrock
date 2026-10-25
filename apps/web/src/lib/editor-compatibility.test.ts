import { createRequire } from "node:module";
import { expect, test } from "vitest";

test("BlockNote's installed ProseMirror graph can track an editor transaction", () => {
  // A stale hoisted Transform previously made the canvas crash with
  // `transaction.changedRange is not a function`, despite a successful build.
  // Resolve through BlockNote so this exercises its actual installed graph.
  const requireFromBlockNote = createRequire(
    import.meta.resolve("@blocknote/core")
  );
  const { EditorState } = requireFromBlockNote("@tiptap/pm/state");
  const { Schema } = requireFromBlockNote("@tiptap/pm/model");
  const state = EditorState.create({
    schema: new Schema({
      nodes: { doc: { content: "text*" }, text: {} },
    }),
  });

  const transaction = state.tr.insertText("canvas");

  expect(transaction.doc.textContent).toBe("canvas");
  expect(transaction.changedRange()).toEqual({ from: 0, to: 6 });
});
