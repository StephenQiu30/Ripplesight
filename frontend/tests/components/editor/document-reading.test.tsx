import { expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { compileMdx } from "nextra/compile";
import { evaluate } from "nextra/evaluate";
import { documentRemark } from "@/components/editor/document-rendering";
import { documentComponents } from "@/components/ui/workspace-markdown";

it("Nextra renders authorized Markdown with application headings, safe links and code", async () => {
  vi.stubEnv("NODE_ENV", "development");
  const snapshot = "a".repeat(64);
  const compiled = await compileMdx(
    "# 中文标题\n\n[计划](/workspace/docs/product/plan/01.md#任务)\n\n```mermaid\ngraph LR\n A --> B\n```\n\n<script>globalThis.executed = true</script>\n",
    {
      mdxOptions: {
        format: "md",
        remarkPlugins: [
          documentRemark([
            { title: "中文标题", anchor: "中文标题", level: 1, content: "" },
          ]),
        ],
      },
      codeHighlight: false,
      isPageImport: false,
      search: false,
    },
  );
  const { default: Content } = evaluate(compiled, documentComponents(snapshot));
  const html = renderToStaticMarkup(<Content />);
  expect(html).toContain('id="中文标题"');
  expect(html).toContain(`?snapshot=${snapshot}#%E4%BB%BB%E5%8A%A1`);
  expect(html).toContain("graph LR");
  expect(html).not.toContain("<script>");
  expect(renderToStaticMarkup(<Content />)).toBe(html);
  vi.unstubAllEnvs();
});
