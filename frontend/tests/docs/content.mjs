import fs from "node:fs";
import path from "node:path";
import { parse as parseYaml } from "yaml";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";

export const repoRoot = path.resolve(import.meta.dirname, "../../..");
export const contentRoot = path.join(repoRoot, "docs");
export const groups = [
  ["product", "产品"],
  ["capabilities", "能力"],
  ["decisions", "决策"],
  ["records", "验收记录"],
  ["research", "调研"],
];
export const excluded = new Set(["templates", "views", ".obsidian", "designs"]);
export const productGroups = [
  ["product/prd", "产品需求（PRD）"],
  ["product/plan", "执行计划（PLAN）"],
  ["product/pages", "页面需求"],
  ["product/reference", "产品参考"],
];
export const markdown = unified().use(remarkParse).use(remarkGfm);

export function walk(directory) {
  return fs
    .readdirSync(directory, { withFileTypes: true })
    .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
    .flatMap((entry) => {
      if (
        entry.name.startsWith(".") ||
        excluded.has(entry.name) ||
        ["README.md", "AGENTS.md", "VERIFICATION.md"].includes(entry.name)
      )
        return [];
      const absolute = path.join(directory, entry.name);
      return entry.isDirectory()
        ? walk(absolute)
        : absolute.endsWith(".md")
          ? [absolute]
          : [];
    });
}

export function readDocument(file, root = contentRoot) {
  const raw = fs.readFileSync(file, "utf8");
  const match = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(raw);
  if (!match) throw new Error("缺少 frontmatter（文件必须以 --- 开头）");
  const relative = path.relative(root, file).split(path.sep).join("/");
  // Parse template placeholders as text while leaving the authored file intact.
  const metadata = relative.startsWith("templates/")
    ? match[1].replaceAll("{{date:YYYY-MM-DD}}", '"{{date:YYYY-MM-DD}}"')
    : match[1];
  const frontmatter = parseYaml(metadata);
  if (
    !frontmatter ||
    typeof frontmatter !== "object" ||
    Array.isArray(frontmatter)
  ) {
    throw new Error("frontmatter 必须是字段映射");
  }
  return { file, relative, raw, body: raw.slice(match[0].length), frontmatter };
}

export function documents(root = contentRoot) {
  return walk(root).map((file) => readDocument(file, root));
}

export function sourceFile(document, sourceRepoRoot = repoRoot) {
  const source = document.frontmatter.source;
  if (!source) return undefined;
  if (typeof source !== "string") throw new Error("source 必须是相对路径");
  const file = path.resolve(path.dirname(document.file), source);
  if (
    !["BACKLOG.md", "PROJECT.md", "AGENTS.md"].some(
      (name) => file === path.join(sourceRepoRoot, name),
    ) ||
    fs.realpathSync(file) !== file
  ) {
    throw new Error(
      "source 只允许指向仓库根目录的 BACKLOG.md、PROJECT.md 或 AGENTS.md 原文",
    );
  }
  return file;
}

export function splitLink(url) {
  const match = /^([^?#]*)([\s\S]*)$/.exec(url);
  return [decodeURIComponent(match[1]), match[2]];
}

export const indexPattern =
  /(<!-- index:start[^\n]*-->)[\s\S]*?(<!-- index:end -->)/;

export function indexBlock(published) {
  const cell = (value) =>
    String(value ?? "—")
      .replaceAll("|", "\\|")
      .replace(/\r?\n/g, " ");
  const table = (items, capability = false) => {
    if (!items.length) return "（暂无）";
    const header = capability
      ? "| 文档 | 摘要 | 状态 | 版本 |\n|---|---|---|---|"
      : "| 文档 | 摘要 | 状态 |\n|---|---|---|";
    const rows = items.map(({ relative, frontmatter: fm }) => {
      const cells = [
        `[${cell(fm.title)}](<${relative}>)`,
        cell(fm.summary),
        cell(fm.status ?? fm.date),
      ];
      if (capability) cells.push(cell(fm.release?.join(", ")));
      return `| ${cells.join(" | ")} |`;
    });
    return [header, ...rows].join("\n");
  };
  return groups
    .map(([folder, title]) => {
      const heading = `### ${title}\n\n`;
      if (folder === "product") {
        return (
          heading +
          productGroups
            .map(([prefix, label]) => {
              const items = published.filter(
                (item) => path.posix.dirname(item.relative) === prefix,
              );
              return `#### ${label}\n\n${table(items)}`;
            })
            .join("\n\n")
        );
      }
      return (
        heading +
        table(
          published.filter((item) => item.relative.startsWith(`${folder}/`)),
          folder === "capabilities",
        )
      );
    })
    .join("\n\n");
}

export function regeneratedIndex(raw, published) {
  if (!indexPattern.test(raw))
    throw new Error("首页缺少唯一的 index:start / index:end 生成标记");
  if (
    (raw.match(/<!-- index:start/g) ?? []).length !== 1 ||
    (raw.match(/<!-- index:end -->/g) ?? []).length !== 1
  ) {
    throw new Error("首页的索引生成标记必须各出现一次");
  }
  return raw.replace(
    indexPattern,
    (_, start, end) => `${start}\n\n${indexBlock(published)}\n\n${end}`,
  );
}
