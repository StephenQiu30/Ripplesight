import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, it } from "vitest";
import { checkDocuments } from "./check.mjs";

const temporary: string[] = [];

afterEach(() => {
  for (const directory of temporary.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

function fixture() {
  const repo = mkdtempSync(path.join(tmpdir(), "ripplesight-docs-test-"));
  temporary.push(repo);
  const root = path.join(repo, "docs");
  mkdirSync(root);
  const page = path.join(root, "PRD.md");
  writeFileSync(page, "# 产品需求\n\n## 用户任务\n");
  return { repo, root, page };
}

function specificationFixture() {
  const result = fixture();
  for (const folder of ["requirement", "prd", "design", "plan"]) {
    mkdirSync(path.join(result.root, folder));
    writeFileSync(path.join(result.root, folder, "00-目标.md"), "# 00 目标\n");
  }
  return result;
}

it("accepts aligned specifications and research outside the numbered set", () => {
  const { repo, root } = specificationFixture();
  mkdirSync(path.join(root, "research"));
  writeFileSync(path.join(root, "research", "调研.md"), "# 调研证据\n");
  expect(checkDocuments(root, repo).errors).toEqual([]);
});

it("rejects a missing human developer handoff", () => {
  const { repo, root } = specificationFixture();
  rmSync(path.join(root, "prd"), { recursive: true });
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(
    "缺少规格目录",
  );
});

it("rejects a renamed specification in only one directory", () => {
  const { repo, root } = specificationFixture();
  writeFileSync(path.join(root, "plan", "01-另一任务.md"), "# 01 另一任务\n");
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(
    "四目录须使用同编号、同名称文件",
  );
});

it.each(["# 00 别名\n", "# 00 目标\n\n# 另一个标题\n", "## 00 目标\n"])(
  "rejects mismatched, duplicated or missing specification titles: %s",
  (content) => {
    const { repo, root } = specificationFixture();
    writeFileSync(path.join(root, "prd", "00-目标.md"), content);
    expect(checkDocuments(root, repo).errors.join("\n")).toContain(
      "规格H1须唯一且与编号名称一致",
    );
  },
);

it("rejects aligned specifications with a numbering gap", () => {
  const { repo, root } = specificationFixture();
  for (const folder of ["requirement", "prd", "design", "plan"]) {
    writeFileSync(path.join(root, folder, "02-跳号.md"), "# 02 跳号\n");
  }
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(
    "规格编号须从00连续",
  );
});

it("accepts continuous specification numbers through 100", () => {
  const { repo, root } = specificationFixture();
  for (const folder of ["requirement", "prd", "design", "plan"]) {
    for (let number = 1; number <= 100; number++) {
      const id = String(number).padStart(2, "0");
      writeFileSync(path.join(root, folder, `${id}-业务.md`), `# ${id} 业务\n`);
    }
  }
  expect(checkDocuments(root, repo).errors).toEqual([]);
});

it("rejects two names for the same specification number", () => {
  const { repo, root } = specificationFixture();
  for (const folder of ["requirement", "prd", "design", "plan"]) {
    writeFileSync(path.join(root, folder, "00-另名.md"), "# 00 另名\n");
  }
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(
    "规格编号须从00连续",
  );
});

it("validates the actual core documents and templates", () => {
  const result = checkDocuments();
  expect(result.errors).toEqual([]);
  expect(result.count).toBeGreaterThan(0);
});

it("accepts plain Markdown without metadata, numbering or a generated index", () => {
  const { repo, root } = fixture();
  writeFileSync(
    path.join(root, "Design.md"),
    "# 设计\n[需求](PRD.md#用户任务)\n",
  );
  expect(checkDocuments(root, repo)).toEqual({ errors: [], count: 2 });
});

it.each([
  ["missing link", "[缺失](missing.md)", "本地链接不存在"],
  ["missing image", "![缺失](missing.png)", "本地链接不存在"],
  ["missing anchor", "[章节](#missing)", "本地锚点不存在"],
  ["invalid encoding", "[章节](%ZZ.md)", "链接编码无效"],
  ["path escape", "[外部文件](../../private.md)", "链接超出仓库"],
])("rejects %s", (_label, link, error) => {
  const { repo, root, page } = fixture();
  writeFileSync(page, readFileSync(page, "utf8") + `\n${link}\n`);
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(error);
});

it("resolves encoded paths, query parameters, duplicate headings and references", () => {
  const { repo, root, page } = fixture();
  writeFileSync(path.join(root, "设计 说明.md"), "# `布局`\n\n## 布局\n");
  writeFileSync(
    page,
    "# 需求\n[规范][design]\n\n[design]: %E8%AE%BE%E8%AE%A1%20%E8%AF%B4%E6%98%8E.md?view=raw#布局-1\n",
  );
  expect(checkDocuments(root, repo).errors).toEqual([]);
});

it("checks templates and ignores links in code, external URLs and private vault state", () => {
  const { repo, root, page } = fixture();
  mkdirSync(path.join(root, "templates"));
  writeFileSync(
    path.join(root, "templates", "示例.md"),
    "[不存在](missing.md)\n",
  );
  mkdirSync(path.join(root, ".obsidian"));
  writeFileSync(
    path.join(root, ".obsidian", "private.md"),
    "[私密](missing.md)\n",
  );
  writeFileSync(
    page,
    "# 需求\n`[代码](missing.md)`\n[网站](https://example.com)\n[邮件](mailto:test@example.com)\n",
  );
  const result = checkDocuments(root, repo);
  expect(result.count).toBe(2);
  expect(result.errors).toEqual([
    "templates/示例.md：本地链接不存在：missing.md",
  ]);
});

it("rejects local links through symlinks pointing outside the repository", () => {
  const { repo, root, page } = fixture();
  const outside = mkdtempSync(path.join(tmpdir(), "ripplesight-docs-outside-"));
  temporary.push(outside);
  writeFileSync(path.join(outside, "private.md"), "# 私密\n");
  symlinkSync(path.join(outside, "private.md"), path.join(root, "linked.md"));
  writeFileSync(page, "[外部文件](linked.md)\n");
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(
    "链接超出仓库",
  );
});
