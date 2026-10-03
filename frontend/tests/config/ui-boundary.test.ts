import { fileURLToPath } from "node:url";
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
  beforeAll(async () => {
    await eslint.calculateConfigForFile("src/app/example/page.tsx");
  });

  it.each(["button", "input", "select", "textarea", "details", "table", "nav"])(
    "rejects a handwritten %s in a page",
    async (tag) => {
      expect(
        await uiViolations(`export default () => <${tag} />;`),
      ).toHaveLength(1);
    },
  );
  it("allows semantic page content and official primitives", async () => {
    expect(
      await uiViolations(
        `export default () => <section><h1>标题</h1><p>正文</p><Button /><Select /><Field /></section>;`,
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
        `export default () => <Item><ItemContent><article className="[&_pre]:rounded-md"><p>正文</p></article><Alert /><Separator /></ItemContent></Item>;`,
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
