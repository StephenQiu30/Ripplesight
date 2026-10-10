import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, expect, it } from "vitest";
import { checkDocuments } from "./check.mjs";
import { documents, regeneratedIndex } from "./content.mjs";

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
  const metadata = (type: string, title: string) =>
    `---\ntype: ${type}\ntitle: ${title}\nsummary: 测试文档\nupdated: 2026-10-10\n---\n\n`;
  const index = path.join(root, "index.md");
  const pages = path.join(root, "product/pages");
  mkdirSync(pages, { recursive: true });
  const page = path.join(pages, "01-example.md");
  writeFileSync(
    index,
    metadata("index", "目录") + "<!-- index:start -->\n<!-- index:end -->\n",
  );
  writeFileSync(page, metadata("pointer", "示例") + "# 示例\n");
  writeFileSync(
    index,
    regeneratedIndex(readFileSync(index, "utf8"), documents(root)),
  );
  return { repo, root, index, page };
}

it("validates the actual project documents through the frontend entry point", () => {
  const result = checkDocuments();
  expect(result.errors).toEqual([]);
  expect(result.count).toBeGreaterThan(0);
});

it("accepts valid local documents and a regenerated index", () => {
  const { repo, root } = fixture();
  expect(checkDocuments(root, repo)).toEqual({ errors: [], count: 2 });
});

it.each([
  ["missing metadata", "updated: 2026-10-10\n", "", "缺少必填字段：updated"],
  ["invalid date", "2026-10-10", "2026-02-30", "必须是有效的 YYYY-MM-DD 日期"],
  ["missing link", "# 示例", "[缺失](missing.md)", "本地链接不存在"],
  ["missing anchor", "# 示例", "[章节](#missing)", "本地锚点不存在"],
  ["vault link", "# 示例", "[[示例]]", "不允许 Obsidian 双链"],
])("rejects %s", (_label, before, after, error) => {
  const { repo, root, page } = fixture();
  writeFileSync(page, readFileSync(page, "utf8").replace(before, after));
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(error);
});

it("rejects duplicate numbering and stale generated indexes", () => {
  const { repo, root, page } = fixture();
  writeFileSync(
    path.join(path.dirname(page), "01-duplicate.md"),
    readFileSync(page, "utf8"),
  );
  const errors = checkDocuments(root, repo).errors.join("\n");
  expect(errors).toContain("编号 01 重复");
  writeFileSync(
    page,
    readFileSync(page, "utf8").replace("title: 示例", "title: 新标题"),
  );
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(
    "索引块已过期",
  );
});

it("keeps root-file pointers restricted to the documented source files", () => {
  const { repo, root, page } = fixture();
  writeFileSync(path.join(repo, "private.md"), "# 私密文件\n");
  writeFileSync(
    page,
    readFileSync(page, "utf8").replace(
      "type: pointer",
      "type: pointer\nsource: ../private.md",
    ),
  );
  expect(checkDocuments(root, repo).errors.join("\n")).toContain(
    "source 只允许指向仓库根目录",
  );
});
