import { fileURLToPath } from "node:url";
import { readFileSync, readdirSync } from "node:fs";
import ts from "typescript";
import { ESLint } from "eslint";
import { beforeAll, describe, expect, it } from "vitest";

const eslint = new ESLint({
  cwd: fileURLToPath(new URL("../..", import.meta.url)),
});
async function uiViolations(
  code: string,
  filePath = "src/app/example/page.tsx",
) {
  const [result] = await eslint.lintText(code, { filePath });
  return result.messages.filter((message) =>
    message.message.includes("shadcn"),
  );
}

describe("official UI component boundary", () => {
  it.each(["app", "components", "layout"])(
    "keeps all %s business JSX inside the UI component boundary",
    (directory) => {
      const root = new URL(`../../src/${directory}/`, import.meta.url);
      const nativeTags: string[] = [];
      const walk = (folder: URL) => {
        for (const entry of readdirSync(folder, { withFileTypes: true })) {
          if (
            directory === "components" &&
            folder.href === root.href &&
            entry.name === "ui"
          )
            continue;
          const path = new URL(
            entry.name + (entry.isDirectory() ? "/" : ""),
            folder,
          );
          if (entry.isDirectory()) {
            walk(path);
            continue;
          }
          if (!entry.name.endsWith(".tsx")) continue;
          const source = ts.createSourceFile(
            path.pathname,
            readFileSync(path, "utf8"),
            ts.ScriptTarget.Latest,
            true,
            ts.ScriptKind.TSX,
          );
          const visit = (node: ts.Node) => {
            if (
              (ts.isJsxOpeningElement(node) ||
                ts.isJsxSelfClosingElement(node)) &&
              ts.isIdentifier(node.tagName) &&
              /^[a-z]/.test(node.tagName.text)
            )
              nativeTags.push(`${path.pathname}: ${node.tagName.text}`);
            ts.forEachChild(node, visit);
          };
          visit(source);
        }
      };
      walk(root);
      expect(nativeTags).toEqual([]);
    },
  );
  beforeAll(async () => {
    await eslint.calculateConfigForFile("src/app/example/page.tsx");
  });

  it.each([
    "button",
    "input",
    "select",
    "textarea",
    "details",
    "table",
    "nav",
    "div",
    "span",
    "section",
    "article",
    "h1",
    "p",
    "form",
    "video",
    "audio",
    "html",
    "body",
  ])("rejects a handwritten %s in a page", async (tag) => {
    expect(await uiViolations(`export default () => <${tag} />;`)).toHaveLength(
      1,
    );
  });
  it("allows UI semantic content and official primitives", async () => {
    expect(
      await uiViolations(
        `export default () => <UI.Content as="section"><UI.Heading level={1}>标题</UI.Heading><UI.Text>正文</UI.Text><Button /><Select /><Field /></UI.Content>;`,
      ),
    ).toHaveLength(0);
    expect(
      await uiViolations(
        `export default () => <button />;`,
        "src/components/ui/button.tsx",
      ),
    ).toHaveLength(0);
  });
  it.each(["bg-muted rounded-lg p-4", "divide-y", "border-t pt-4"])(
    "rejects a handmade surface or separator: %s",
    async (className) => {
      expect(
        await uiViolations(
          `export default () => <section className="${className}" />;`,
        ),
      ).toHaveLength(1);
    },
  );
  it("allows semantic article styling and official surfaces", async () => {
    expect(
      await uiViolations(
        `export default () => <Item><ItemContent><UI.Content as="article"><UI.Text>正文</UI.Text></UI.Content><Alert /><Separator /></ItemContent></Item>;`,
      ),
    ).toHaveLength(0);
  });
  it("rejects a handwritten status message", async () => {
    expect(
      await uiViolations(`export default () => <p role="status">正在读取</p>;`),
    ).toHaveLength(1);
  });
  it("rejects a handmade clickable container", async () => {
    expect(
      await uiViolations(`export default () => <div role="button" />;`),
    ).toHaveLength(1);
  });
  it.each(["div", "span", "p"])(
    "rejects a handmade %s error alert",
    async (tag) => {
      expect(
        await uiViolations(
          `export default () => <${tag} role="alert">失败</${tag}>;`,
        ),
      ).toHaveLength(1);
    },
  );
});
