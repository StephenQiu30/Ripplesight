import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  Viewer,
  markdownToDocument,
  normalizeDocument,
  documentToText,
  textToDocument,
} from "@/components/editor";
import { documentToHtml } from "@/components/editor/content";

describe("Editor.js content compatibility", () => {
  it("preserves the official ordered-list counter and nested metadata", () => {
    const document = normalizeDocument({
      blocks: [
        {
          type: "list",
          data: {
            style: "ordered",
            meta: { start: 3, counterType: "upper-roman" },
            items: [
              {
                content: "内容",
                meta: { start: 2, counterType: "lower-alpha" },
                items: [{ content: "子项", meta: {}, items: [] }],
              },
            ],
          },
        },
      ],
    });
    expect(document!.blocks[0].data.meta.counterType).toBe("upper-roman");
    expect(documentToHtml(document!)).toContain('<ol start="3" type="I">');
    expect(documentToHtml(document!)).toContain('<ol start="2" type="a">');
  });
  it("renders Markdown as semantic blocks including nested/check lists, code and tables", () => {
    const document = markdownToDocument(
      "# 标题\n\n**重点**与`代码`\n\n3. 第三项\n   - 子项\n4. 第四项\n\n- [x] 完成\n- [ ] 待办\n\n> 引用\n\n```js\n<script>bad()</script>\n```\n\n| 名称 | 数量 |\n| --- | --- |\n| A | 2 |\n\n---\n\n![配图](https://example.com/image.png)",
    );
    expect(document.blocks.map(({ type }) => type)).toEqual([
      "header",
      "paragraph",
      "list",
      "list",
      "quote",
      "code",
      "table",
      "delimiter",
      "image",
    ]);
    const html = documentToHtml(document, 1);
    expect(html).toContain("<h2>标题</h2>");
    expect(html).toContain("<strong>重点</strong>");
    expect(html).toContain('<ol start="3" type="1">');
    expect(html).toContain("<ul><li>子项</li></ul>");
    expect(html).toContain("☑ 完成");
    expect(html).toContain("☐ 待办");
    expect(html).toContain("&lt;script&gt;bad()&lt;/script&gt;");
    expect(html).toContain("<th>名称</th>");
    expect(html).toContain('alt="配图"');
    expect(normalizeDocument(document)).toBeTruthy();
  });

  it("resolves frozen citations only in prose and preserves missing/unsafe citations", () => {
    const document = markdownToDocument(
      "材料 [c1] [c2] [c3]\n\n`[c1]`\n\n[原帖](<https://example.com/post?q=1&v=2>)",
      [
        { citation: "c1", url: "https://example.com/source" },
        { citation: "c2", url: "javascript:alert(1)" },
      ],
    );
    const html = documentToHtml(document);
    expect(html.match(/href="https:\/\/example.com\/source"/g)).toHaveLength(1);
    expect(html).toContain("[c2] [c3]");
    expect(html).toContain("<code>[c1]</code>");
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("原帖</a>");
    expect(html).not.toContain("javascript:");
  });

  it("sanitizes legacy HTML and stored JSON before rendering or editing", () => {
    const value =
      '<h2 id="section">正文</h2><script>alert(1)</script><img src="javascript:alert(1)" onerror="alert(2)"><a href="data:text/html,bad">链接</a><iframe src="https://evil.example"></iframe>';
    const html = renderToStaticMarkup(<Viewer value={value} format="html" />);
    expect(html).toContain('id="section"');
    expect(html).not.toMatch(/script|javascript|onerror|iframe|data:text/);
    expect(
      renderToStaticMarkup(
        <Viewer
          value='<video controls src="/media/video.mp4"><source src="https://example.com/media.mp4" type="video/mp4"></video>'
          format="html"
        />,
      ),
    ).toContain('<video controls src="/media/video.mp4">');
    const document = normalizeDocument({
      blocks: [
        {
          type: "paragraph",
          data: {
            text: "<img src=x onerror=alert(1)><b onclick=bad()>保留</b>",
          },
        },
      ],
    });
    expect(document?.blocks[0].data.text).toBe("<b>保留</b>");
    expect(
      normalizeDocument({
        blocks: [{ type: "list", data: { items: [null] } }],
      }),
    ).toBeNull();
    expect(
      normalizeDocument({
        blocks: [{ type: "table", data: { content: ["bad"] } }],
      }),
    ).toBeNull();
    expect(
      normalizeDocument({ blocks: [{ type: "unknown", data: {} }] }),
    ).toBeNull();
  });

  it("renders on the server without a browser and keeps plain text notes readable", () => {
    const value = "旧笔记 <tag> & 继续\n第二行";
    expect(documentToText(textToDocument(value))).toBe(value);
    const html = renderToStaticMarkup(<Viewer value={textToDocument(value)} />);
    expect(html).toContain("旧笔记 &lt;tag&gt; &amp; 继续<br />");
    expect(html).not.toContain("contenteditable");
    expect(renderToStaticMarkup(<Viewer value="" />)).not.toContain(
      "undefined",
    );
  });
});
