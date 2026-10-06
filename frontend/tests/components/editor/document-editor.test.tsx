// @vitest-environment happy-dom
import { createRef } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  DocumentEditor,
  type DocumentEditorHandle,
} from "@/components/ui/document-editor";

afterEach(cleanup);

it("loads the real Editor.js bundle and preserves raw source through its saver", async () => {
  const markdown =
    "---\ncustom: keep\n---\n\n# 标题\n\n段落 **强调**\n\n<!-- 原注释 -->\n\n```mermaid\ngraph LR\n A --> B\n```\n";
  const ref = createRef<DocumentEditorHandle>();
  render(<DocumentEditor markdown={markdown} onChange={vi.fn()} ref={ref} />);
  const paragraph = await screen.findByRole("textbox", { name: "文档段落" });
  await waitFor(async () => expect(await ref.current?.read()).toBe(markdown));
  expect(screen.queryByRole("alert")).toBeNull();
  paragraph.innerHTML = "中文<strong>修改</strong>";
  expect(await ref.current?.read()).toBe(
    markdown.replace("段落 **强调**", "中文**修改**"),
  );
});
