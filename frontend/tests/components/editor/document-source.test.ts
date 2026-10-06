// @vitest-environment happy-dom
import { decodeDocumentPath } from "@/components/editor/document-path";
import { describe, expect, it } from "vitest";
import {
  sourceBlocks,
  sourceMarkdown,
} from "@/components/editor/document-source";
import { safeDocumentHref } from "@/components/ui/workspace-markdown";

describe("document Markdown preservation", () => {
  it.each([
    "---\ntype: prd\ncustom: {unknown: true}\n# 元数据注释\n---\n\n# 需求\n\n原文 **强调** 与 [链接](../plan/01-计划.md#任务)。\n",
    "## 标题\r\n\r\n中文段落\r\n\r\n<!-- 注释保留 -->\r\n",
    "```mermaid\ngraph LR\n A --> B\n```\n\n```python\nprint('语言保留')\n```\n",
    "| 名称 | 值 |\n|---|---|\n| 字段 | `code` |\n\n- [x] 已完成\n- [ ] 等待\n",
    '[引用][ref]\n\n[ref]: ../document.md "标题"\n\n自定义 $公式$ 和 [[不被转换的草稿语法]]\n',
    "\n\n尾部无换行",
  ])("unchanged view round trips preserve every byte", (markdown) => {
    expect(sourceMarkdown(sourceBlocks(markdown))).toBe(markdown);
  });

  it("paragraph edits preserve surrounding code, metadata and blank lines", () => {
    const original =
      "---\ncustom: keep\n---\n\n原段落\n\n```ts\nconst value = 1;\n```\n";
    const blocks = sourceBlocks(original);
    const paragraph = blocks.blocks.find(
      (item) => item.data.kind === "paragraph",
    );
    expect(paragraph).toBeDefined();
    paragraph!.data.html = "中文<strong>修改</strong>";
    expect(sourceMarkdown(blocks)).toBe(
      original.replace("原段落", "中文**修改**"),
    );
  });

  it("pasted scripts and unsafe media cannot become executable HTML", () => {
    const data = sourceBlocks("段落\n");
    data.blocks[0].data.html =
      '<script>alert(1)</script><a href="javascript:alert(1)">标题</a><img src="x" onerror="alert(1)">';
    expect(sourceMarkdown(data)).not.toMatch(/script|javascript:|onerror/i);
  });
});

it("document and attachment links stay on the chosen snapshot and reject unsafe URLs", () => {
  const snapshot = "a".repeat(64);
  expect(safeDocumentHref("/workspace/docs/product/01.md#任务", snapshot)).toBe(
    `/workspace/docs/product/01.md?snapshot=${snapshot}#任务`,
  );
  expect(
    safeDocumentHref("workspace-attachment:" + "b".repeat(64), snapshot),
  ).toContain(
    `/api/workspace/documents/attachment?attachment_id=${"b".repeat(64)}&snapshot_id=${snapshot}`,
  );
  expect(safeDocumentHref("javascript:alert(1)", snapshot)).toBeUndefined();
  expect(safeDocumentHref("//outside.example", snapshot)).toBeUndefined();
  expect(safeDocumentHref("file:///etc/hosts", snapshot)).toBeUndefined();
  expect(
    safeDocumentHref("/workspace/docs/decisions/01.md#原规则", snapshot, true),
  ).toBe(
    `/workspace/docs/decisions/01.md?snapshot=${snapshot}&history=true#原规则`,
  );
  expect(
    safeDocumentHref("workspace-attachment:" + "b".repeat(64), snapshot, true),
  ).toContain("&history=true");
});

it("decodes Chinese route segments once and rejects encoded traversal", () => {
  const path = "product/prd/02-PRD-workspace项目知识库.md";
  expect(decodeDocumentPath(path.split("/").map(encodeURIComponent))).toBe(
    path,
  );
  expect(() => decodeDocumentPath(["%2e%2e", "PROJECT.md"])).toThrow();
  expect(() => decodeDocumentPath(["product%2f..%2fPROJECT.md"])).toThrow();
  expect(() => decodeDocumentPath(["%zz"])).toThrow();
});
