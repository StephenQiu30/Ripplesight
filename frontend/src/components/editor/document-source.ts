import { marked } from "marked";
import type { OutputData } from "@editorjs/editorjs";
import TurndownService from "turndown";
import { cleanHtml } from "./content";

export type SourceBlock = {
  kind: "paragraph" | "heading" | "raw";
  raw: string;
  html: string;
  originalHtml: string;
  depth?: number;
  suffix: string;
};
const converter = new TurndownService({
  headingStyle: "atx",
  codeBlockStyle: "fenced",
  bulletListMarker: "-",
});
export function sourceBlocks(markdown: string): OutputData {
  const blocks: { type: string; data: SourceBlock }[] = [];
  const metadata =
    /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/.exec(markdown)?.[0] ?? "";
  if (metadata)
    blocks.push({
      type: "source",
      data: {
        kind: "raw",
        raw: metadata,
        html: "",
        originalHtml: "",
        suffix: "",
      },
    });
  for (const token of marked.lexer(markdown.slice(metadata.length))) {
    if (token.type === "space" && blocks.length) {
      blocks[blocks.length - 1].data.raw += token.raw;
      blocks[blocks.length - 1].data.suffix += token.raw;
      continue;
    }
    const kind =
      token.type === "paragraph"
        ? "paragraph"
        : token.type === "heading"
          ? "heading"
          : "raw";
    const html =
      kind === "raw"
        ? ""
        : cleanHtml(
            String(
              marked.parseInline("text" in token ? String(token.text) : ""),
            ),
            true,
          );
    blocks.push({
      type: "source",
      data: {
        kind,
        raw: token.raw,
        html,
        originalHtml: html,
        depth: "depth" in token ? Number(token.depth) : undefined,
        suffix: token.raw.match(/(?:\r?\n)+$/)?.[0] ?? "",
      },
    });
  }
  // Reference definitions and lexer normalization must never drop authored bytes.
  if (blocks.map((block) => block.data.raw).join("") !== markdown)
    return {
      blocks: [
        {
          type: "source",
          data: {
            kind: "raw",
            raw: markdown,
            html: "",
            originalHtml: "",
            suffix: "",
          },
        },
      ],
    };
  return { blocks };
}
export function sourceMarkdown(data: OutputData): string {
  return data.blocks
    .map((block) => {
      const item = block.data as SourceBlock;
      if (
        item.kind === "raw" ||
        cleanHtml(item.html, true) === item.originalHtml
      )
        return item.raw;
      const text = converter.turndown(cleanHtml(item.html, true));
      return (
        (item.kind === "heading" ? "#".repeat(item.depth ?? 2) + " " : "") +
        text +
        (item.suffix || (item.raw ? "" : "\n\n"))
      );
    })
    .join("");
}
