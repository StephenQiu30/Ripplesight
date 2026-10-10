import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import GithubSlugger from "github-slugger";
import { visit } from "unist-util-visit";
import {
  contentRoot,
  repoRoot,
  walk,
  readDocument,
  documents,
  markdown,
  regeneratedIndex,
  sourceFile,
  splitLink,
} from "./content.mjs";

const common = ["type", "title", "summary", "updated"];
const fields = {
  capability: [...common, "status", "release", "kr"],
  decision: [...common, "status", "decided", "related"],
  record: [...common, "capability", "criterion", "result", "date"],
  research: [...common, "date"],
  prd: [...common, "status"],
  plan: [...common, "status"],
  pointer: common,
  glossary: common,
  index: common,
};
const enums = {
  capability: ["可用", "部分可用", "未开始", "冻结"],
  decision: ["生效", "废弃"],
  prd: ["生效", "废弃", "草稿"],
  plan: ["生效", "废弃", "草稿"],
};
const limits = {
  capability: 6000,
  decision: 2000,
  record: 2000,
  prd: 12000,
  plan: 12000,
};
const inside = (directory, file) =>
  file === directory || file.startsWith(directory + path.sep);
const text = (node) => node.value ?? (node.children ?? []).map(text).join("");

function anchors(body) {
  const slugger = new GithubSlugger();
  const ids = new Set();
  visit(markdown.parse(body), "heading", (node) =>
    ids.add(slugger.slug(text(node))),
  );
  return ids;
}

export function checkDocuments(root = contentRoot, sourceRepoRoot = repoRoot) {
  const errors = [];
  const fail = (file, message) =>
    errors.push(`${path.relative(root, file) || "docs/"}：${message}`);
  const published = [];
  for (const file of walk(root)) {
    try {
      published.push(readDocument(file, root));
    } catch (error) {
      fail(file, `frontmatter 无效：${error.message}`);
    }
  }

  function names(directory) {
    const numbers = new Map();
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if ([".obsidian", "designs"].includes(entry.name)) continue;
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!/^[a-z]+$/.test(entry.name))
          fail(file, "文件夹必须使用小写英文字母");
        names(file);
        continue;
      }
      if (
        !/\.(?:md|base)$/.test(entry.name) ||
        (directory === root &&
          ["index.md", "README.md", "AGENTS.md", "VERIFICATION.md"].includes(
            entry.name,
          ))
      )
        continue;
      const dateFolder = ["records", "research"].includes(
        path.relative(root, directory),
      );
      const numbered = /^(\d{2})-.+\.(md|base)$/.exec(entry.name);
      const dated = dateFolder && /^\d{4}-\d{2}-\d{2}-.+\.md$/.test(entry.name);
      if (!numbered && !dated)
        fail(
          file,
          "文件名必须为“两位编号-名称”，记录和调研也可用“YYYY-MM-DD-名称.md”",
        );
      if (numbered) {
        if (numbered[1] === "00") fail(file, "文档编号从 01 开始，不能使用 00");
        if (numbers.has(numbered[1]))
          fail(
            file,
            `编号 ${numbered[1]} 重复（另一个文件：${numbers.get(numbered[1])}）`,
          );
        numbers.set(numbered[1], entry.name);
      }
    }
  }
  names(root);

  const byFile = new Map(published.map((item) => [item.file, item]));
  const anchorsByFile = new Map();
  function localLinks(body, origin) {
    const tree = markdown.parse(body);
    visit(tree, "text", (node) => {
      if (/\[\[[^\]\n]+\]\]/.test(node.value))
        fail(origin, "不允许 Obsidian 双链，请使用标准 Markdown 链接");
    });
    const definitions = new Set();
    visit(tree, "definition", (node) => definitions.add(node.identifier));
    visit(tree, (node) => {
      if (
        ["linkReference", "imageReference"].includes(node.type) &&
        !definitions.has(node.identifier)
      ) {
        fail(origin, `链接引用未定义：${node.identifier}`);
      }
      if (!["link", "image", "definition"].includes(node.type)) return;
      if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(node.url)) return;
      let target, suffix;
      try {
        [target, suffix] = splitLink(node.url);
      } catch {
        fail(origin, `链接编码无效：${node.url}`);
        return;
      }
      const file = target ? path.resolve(path.dirname(origin), target) : origin;
      if (!inside(sourceRepoRoot, file) && !inside(root, file)) {
        fail(origin, `链接超出仓库：${node.url}`);
        return;
      }
      if (!fs.existsSync(file)) {
        fail(origin, `本地链接不存在：${node.url}`);
        return;
      }
      const hash = suffix.indexOf("#");
      if (hash < 0 || !file.endsWith(".md")) return;
      let anchor;
      try {
        anchor = decodeURIComponent(suffix.slice(hash + 1));
      } catch {
        fail(origin, `锚点编码无效：${node.url}`);
        return;
      }
      if (!anchor) return;
      if (!anchorsByFile.has(file)) {
        const linked = byFile.get(file);
        let linkedBody = linked?.body ?? fs.readFileSync(file, "utf8");

        anchorsByFile.set(file, anchors(linkedBody));
      }
      if (!anchorsByFile.get(file).has(anchor))
        fail(origin, `本地锚点不存在：${node.url}`);
    });
  }

  for (const document of published) {
    const { file, frontmatter: fm, body } = document;
    const required = fields[fm.type];
    if (!required) {
      fail(file, `未知文档类型：${fm.type ?? "未填写"}`);
      continue;
    }
    const relative = path.relative(root, file).split(path.sep).join("/");
    if (fm.type === "prd" && !relative.startsWith("product/prd/"))
      fail(file, "PRD 必须位于 product/prd/");
    if (fm.type === "plan" && !relative.startsWith("product/plan/"))
      fail(file, "PLAN 必须位于 product/plan/");
    for (const key of required) {
      if (
        !(key in fm) ||
        fm[key] == null ||
        (typeof fm[key] === "string" && !fm[key].trim())
      ) {
        fail(file, `缺少必填字段：${key}`);
      }
    }
    for (const key of [
      "type",
      "title",
      "summary",
      "updated",
      "status",
      "decided",
      "date",
    ]) {
      if (key in fm && typeof fm[key] !== "string")
        fail(file, `字段 ${key} 必须是字符串`);
    }
    if ("visibility" in fm && !["public", "private"].includes(fm.visibility))
      fail(file, "visibility 只能为 public / private");
    for (const key of ["updated", "decided", "date"]) {
      if (
        key in fm &&
        (!/^\d{4}-\d{2}-\d{2}$/.test(fm[key]) ||
          Number.isNaN(Date.parse(fm[key])) ||
          new Date(fm[key]).toISOString().slice(0, 10) !== fm[key])
      ) {
        fail(file, `字段 ${key} 必须是有效的 YYYY-MM-DD 日期`);
      }
    }
    if (enums[fm.type] && !enums[fm.type].includes(fm.status))
      fail(file, `状态无效：${fm.status}；可选 ${enums[fm.type].join(" / ")}`);
    if (fm.type === "record" && !["通过", "未通过"].includes(fm.result))
      fail(file, "验收结果必须是 通过 / 未通过");
    for (const key of ["release", "kr", "related"]) {
      if (
        key in fm &&
        (!Array.isArray(fm[key]) ||
          fm[key].some((value) => typeof value !== "string" || !value.trim()))
      ) {
        fail(file, `字段 ${key} 必须是字符串数组`);
      }
    }
    if (
      Array.isArray(fm.release) &&
      fm.release.some((value) => !["V1", "V2", "以后"].includes(value))
    )
      fail(file, "release 只能包含 V1 / V2 / 以后");
    const references = [
      ...(Array.isArray(fm.related) ? fm.related : []),
      ...(fm.capability ? [fm.capability] : []),
    ];
    for (const reference of references) {
      if (typeof reference !== "string") {
        fail(file, "related / capability 必须使用相对 docs/ 的路径");
        continue;
      }
      const target = path.resolve(root, reference);
      if (
        path.isAbsolute(reference) ||
        !inside(root, target) ||
        !byFile.has(target)
      )
        fail(file, `关联文档不存在：${reference}`);
      else if (
        reference === fm.capability &&
        byFile.get(target).frontmatter.type !== "capability"
      )
        fail(file, `capability 必须指向能力文档：${reference}`);
    }
    if (limits[fm.type] && [...body].length > limits[fm.type])
      fail(
        file,
        `正文超过 ${limits[fm.type]} 字符（当前 ${[...body].length}）`,
      );
    localLinks(body, file);
    if (fm.source) {
      try {
        localLinks(
          fs.readFileSync(sourceFile(document, sourceRepoRoot), "utf8"),
          sourceFile(document, sourceRepoRoot),
        );
      } catch (error) {
        fail(file, `根文件指针无效：${error.message}`);
      }
    }
  }
  let indexedDocuments = [];
  try {
    indexedDocuments = documents(root);
  } catch (error) {
    fail(root, `文档目录无效：${error.message}`);
  }
  const index = indexedDocuments.find((item) => item.relative === "index.md");
  if (!index) fail(path.join(root, "index.md"), "缺少首页");
  else {
    try {
      if (regeneratedIndex(index.raw, indexedDocuments) !== index.raw)
        fail(index.file, "索引块已过期，请执行 pnpm docs:index");
    } catch (error) {
      fail(index.file, `索引块无效：${error.message}`);
    }
  }
  return { errors, count: indexedDocuments.length };
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    const { errors, count } = checkDocuments();
    if (errors.length) {
      console.error(
        `文档检查失败（${errors.length} 项）：\n${errors.map((error) => `- ${error}`).join("\n")}`,
      );
      process.exitCode = 1;
    } else
      console.log(
        `文档检查通过：${count} 份文档，元数据、命名、索引和本地链接有效。`,
      );
  } catch (error) {
    console.error(`文档检查失败：${error.message}`);
    process.exitCode = 1;
  }
}
