import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import GithubSlugger from "github-slugger";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";

const repoRoot = path.resolve(import.meta.dirname, "../../..");
const contentRoot = path.join(repoRoot, "docs");
const markdown = unified().use(remarkParse).use(remarkGfm);
const inside = (directory, file) =>
  file === directory || file.startsWith(directory + path.sep);
const text = (node) => node.value ?? (node.children ?? []).map(text).join("");
const body = (file) =>
  fs
    .readFileSync(file, "utf8")
    .replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, "");

const specificationFolders = ["requirement", "prd", "design", "plan"];

function checkSpecificationSet(root, fail) {
  // Plain Markdown workspaces remain valid; numbered product specifications
  // use one shared traceability key across all four handoff documents.
  if (
    !specificationFolders.some((folder) =>
      fs.existsSync(path.join(root, folder)),
    )
  )
    return;
  const sets = specificationFolders.map((folder) => {
    const directory = path.join(root, folder);
    if (!fs.existsSync(directory) || !fs.statSync(directory).isDirectory()) {
      fail(directory, "缺少规格目录");
      return new Set();
    }
    return new Set(
      documents(directory).map((file) => path.relative(directory, file)),
    );
  });
  const names = [...new Set(sets.flatMap((set) => [...set]))].sort(
    (left, right) =>
      Number.parseInt(left, 10) - Number.parseInt(right, 10) ||
      left.localeCompare(right),
  );
  if (!names.length) fail(root, "规格目录不能为空");
  names.forEach((name, index) => {
    const match = /^(\d{2,})-([^/\\]+)\.md$/.exec(name);
    if (!match || Number(match[1]) !== index)
      fail(
        path.join(root, "requirement", name),
        "规格编号须从00连续且每编号唯一",
      );
    specificationFolders.forEach((folder, folderIndex) => {
      const file = path.join(root, folder, name);
      if (!sets[folderIndex].has(name)) {
        fail(file, "四目录须使用同编号、同名称文件");
        return;
      }
      const tree = markdown.parse(body(file));
      const titles = tree.children.filter(
        (node) => node.type === "heading" && node.depth === 1,
      );
      const expected = match ? `${match[1]} ${match[2]}` : "";
      if (titles.length !== 1 || text(titles[0]) !== expected)
        fail(file, "规格H1须唯一且与编号名称一致");
    });
  });
}

function documents(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name.startsWith(".")) return [];
    const file = path.join(directory, entry.name);
    return entry.isDirectory()
      ? documents(file)
      : entry.isFile() && entry.name.endsWith(".md")
        ? [file]
        : [];
  });
}

export function checkDocuments(root = contentRoot, sourceRepoRoot = repoRoot) {
  root = fs.realpathSync(root);
  sourceRepoRoot = fs.realpathSync(sourceRepoRoot);
  const files = documents(root);
  const errors = [];
  const headings = new Map();
  const fail = (file, message) =>
    errors.push(`${path.relative(root, file)}：${message}`);

  checkSpecificationSet(root, fail);

  for (const origin of files) {
    visit(markdown.parse(body(origin)), (node) => {
      if (!["link", "image", "definition"].includes(node.type)) return;
      if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(node.url)) return;
      let target, anchor;
      try {
        target = decodeURIComponent(/^[^?#]*/.exec(node.url)[0]);
        const hash = node.url.indexOf("#");
        anchor = hash < 0 ? "" : decodeURIComponent(node.url.slice(hash + 1));
      } catch {
        fail(origin, `链接编码无效：${node.url}`);
        return;
      }
      const file = target ? path.resolve(path.dirname(origin), target) : origin;
      if (!inside(sourceRepoRoot, file)) {
        fail(origin, `链接超出仓库：${node.url}`);
        return;
      }
      if (!fs.existsSync(file)) {
        fail(origin, `本地链接不存在：${node.url}`);
        return;
      }
      if (!inside(sourceRepoRoot, fs.realpathSync(file))) {
        fail(origin, `链接超出仓库：${node.url}`);
        return;
      }
      if (!anchor || !file.endsWith(".md")) return;
      if (!headings.has(file)) {
        const slugger = new GithubSlugger();
        const ids = new Set();
        visit(markdown.parse(body(file)), "heading", (heading) =>
          ids.add(slugger.slug(text(heading))),
        );
        headings.set(file, ids);
      }
      if (!headings.get(file).has(anchor))
        fail(origin, `本地锚点不存在：${node.url}`);
    });
  }
  return { errors, count: files.length };
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    const { errors, count } = checkDocuments();
    if (errors.length) {
      console.error(errors.join("\n"));
      process.exitCode = 1;
    } else
      console.log(
        `文档检查通过：${count} 份 Markdown，四类规格结构、本地链接与锚点有效。`,
      );
  } catch (error) {
    console.error(`文档检查失败：${error.message}`);
    process.exitCode = 1;
  }
}
