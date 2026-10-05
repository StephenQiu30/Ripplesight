import type { OutputData, OutputBlockData } from "@editorjs/editorjs";
import { marked, type Token, type Tokens } from "marked";
import sanitizeHtml from "sanitize-html";

export type EditorDocument = OutputData;
export type ContentFormat = "markdown" | "html" | "text";
export type ContentValue = EditorDocument | string;
export type ContentCitation = { citation: string; url?: string | null };

const inlineTags = [
  "a",
  "b",
  "strong",
  "i",
  "em",
  "s",
  "del",
  "u",
  "code",
  "br",
  "mark",
  "sub",
  "sup",
];

export function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ]!,
  );
}

/** One sanitizer for legacy HTML, block data and editor input. No scripts, frames or event attributes. */
export function cleanHtml(value: string, inline = false): string {
  return sanitizeHtml(value, {
    allowedTags: inline
      ? inlineTags
      : [
          ...inlineTags,
          "p",
          "div",
          "span",
          "h1",
          "h2",
          "h3",
          "h4",
          "h5",
          "h6",
          "blockquote",
          "pre",
          "ul",
          "ol",
          "li",
          "table",
          "thead",
          "tbody",
          "tr",
          "th",
          "td",
          "hr",
          "img",
          "figure",
          "figcaption",
          "video",
          "audio",
          "source",
        ],
    allowedAttributes: {
      a: ["href", "title", "target", "rel"],
      img: ["src", "alt", "title"],
      video: ["src", "controls", "poster", "preload"],
      audio: ["src", "controls", "preload"],
      source: ["src", "type"],
      "*": ["id"],
      ol: ["start", "type"],
      li: ["value"],
      th: ["colspan", "rowspan"],
      td: ["colspan", "rowspan"],
    },
    allowedSchemes: ["https", "http", "mailto"],
    allowedSchemesByTag: {
      img: ["https", "http"],
      video: ["https", "http"],
      audio: ["https", "http"],
      source: ["https", "http"],
    },
    allowProtocolRelative: false,
    transformTags: {
      a: (_tag, attributes) => ({
        tagName: "a",
        attribs: {
          ...attributes,
          target: "_blank",
          rel: "noopener noreferrer",
        },
      }),
    },
  });
}

function safeCitationUrl(value?: string | null): string | null {
  try {
    const url = new URL(value ?? "");
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function addCitations(
  tokens: Token[],
  citations: Map<string, string | null>,
): void {
  for (const token of tokens) {
    if (token.type === "text") {
      const text = token as Tokens.Text;
      // Work on text tokens only: never alter URLs, code, HTML or link labels.
      text.text = text.text.replace(
        /\[(c[1-9][0-9]*)\]/g,
        (label, id: string) => {
          const url = citations.get(id);
          return url ? `<a href="${escapeHtml(url)}">${label}</a>` : label;
        },
      );
    } else if (
      token.type !== "link" &&
      token.type !== "code" &&
      token.type !== "codespan" &&
      "tokens" in token &&
      token.tokens
    ) {
      addCitations(token.tokens, citations);
    }
  }
}

export function textToDocument(value: string): EditorDocument {
  return {
    blocks: value
      ? value.split(/\n\s*\n/).map((text) => ({
          type: "paragraph",
          data: { text: escapeHtml(text).replace(/\n/g, "<br>") },
        }))
      : [],
  };
}

export function markdownToDocument(
  value: string,
  references: readonly ContentCitation[] = [],
): EditorDocument {
  const citations = new Map(
    references.map((reference) => [
      reference.citation,
      safeCitationUrl(reference.url),
    ]),
  );
  const inline = (tokens: Token[]) => {
    addCitations(tokens, citations);
    return cleanHtml(new marked.Parser().parseInline(tokens), true);
  };
  const inlineText = (text: string) => {
    const tokens = marked.lexer(text)[0];
    return tokens && "tokens" in tokens && tokens.tokens
      ? inline(tokens.tokens)
      : cleanHtml(marked.parseInline(text) as string, true);
  };
  const listItems = (items: Tokens.ListItem[]): Record<string, unknown>[] =>
    items.map((item) => ({
      content: item.tokens
        .filter((token) => token.type !== "list" && token.type !== "checkbox")
        .map((token) =>
          "tokens" in token && token.tokens
            ? inline(token.tokens)
            : inlineText(token.raw),
        )
        .join("<br>"),
      meta: {
        ...(item.task ? { checked: !!item.checked } : {}),
        ...(item.tokens.some((token) => token.type === "list")
          ? {
              nestedStyle: (
                item.tokens.find(
                  (token) => token.type === "list",
                ) as Tokens.List
              ).ordered
                ? "ordered"
                : "unordered",
              nestedStart: (
                item.tokens.find(
                  (token) => token.type === "list",
                ) as Tokens.List
              ).start,
            }
          : {}),
      },
      items: item.tokens
        .filter((token): token is Tokens.List => token.type === "list")
        .flatMap((list) => listItems(list.items)),
    }));
  const blocks: OutputBlockData[] = [];
  for (const token of marked.lexer(value, { gfm: true })) {
    switch (token.type) {
      case "space":
      case "def":
        break;
      case "heading": {
        const heading = token as Tokens.Heading;
        blocks.push({
          type: "header",
          data: { text: inline(heading.tokens), level: heading.depth },
        });
        break;
      }
      case "paragraph":
      case "text": {
        const paragraph = token as Tokens.Paragraph;
        if (
          paragraph.tokens?.length === 1 &&
          paragraph.tokens[0].type === "image"
        ) {
          const image = paragraph.tokens[0] as Tokens.Image;
          blocks.push({
            type: "image",
            data: { url: image.href, caption: escapeHtml(image.text) },
          });
        } else {
          blocks.push({
            type: "paragraph",
            data: {
              text: paragraph.tokens
                ? inline(paragraph.tokens)
                : inlineText(paragraph.text),
            },
          });
        }
        break;
      }
      case "list": {
        const list = token as Tokens.List;
        blocks.push({
          type: "list",
          data: {
            style: list.items.some((item) => item.task)
              ? "checklist"
              : list.ordered
                ? "ordered"
                : "unordered",
            meta: list.ordered ? { start: list.start } : {},
            items: listItems(list.items),
          },
        });
        break;
      }
      case "blockquote": {
        const quote = token as Tokens.Blockquote;
        blocks.push({
          type: "quote",
          data: {
            text: cleanHtml(marked.parser(quote.tokens))
              .replace(/<\/?p>/g, "")
              .trim(),
            caption: "",
            alignment: "left",
          },
        });
        break;
      }
      case "code":
        blocks.push({
          type: "code",
          data: { code: (token as Tokens.Code).text },
        });
        break;
      case "table": {
        const table = token as Tokens.Table;
        blocks.push({
          type: "table",
          data: {
            withHeadings: true,
            content: [table.header, ...table.rows].map((row) =>
              row.map((cell) => inline(cell.tokens)),
            ),
          },
        });
        break;
      }
      case "hr":
        blocks.push({ type: "delimiter", data: {} });
        break;
      default:
        blocks.push(...textToDocument(token.raw).blocks);
    }
  }
  return { blocks };
}

const string = (value: unknown): string =>
  typeof value === "string" ? value : "";
const items = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter((item) => item && typeof item === "object")
    : [];
const integer = (value: unknown, fallback: number) =>
  typeof value === "number" && Number.isInteger(value) ? value : fallback;

function renderList(data: Record<string, unknown>, depth = 0): string {
  if (depth > 20) return "";
  const ordered = data.style === "ordered";
  const tag = ordered ? "ol" : "ul";
  const meta = data.meta as Record<string, unknown> | undefined;
  const start = Math.max(1, integer(meta?.start, 1));
  const counterType =
    (
      {
        "upper-roman": "I",
        "lower-roman": "i",
        "upper-alpha": "A",
        "lower-alpha": "a",
      } as Record<string, string>
    )[string(meta?.counterType)] ?? "1";
  const content = (Array.isArray(data.items) ? data.items : [])
    .map((value: unknown) => {
      if (!value || typeof value !== "object") return "";
      const item = value as Record<string, unknown>;
      const itemMeta = item.meta as Record<string, unknown> | undefined;
      const marker =
        data.style === "checklist" ? (itemMeta?.checked ? "☑ " : "☐ ") : "";
      return `<li>${marker}${cleanHtml(string(item.content), true)}${items(item.items).length ? renderList({ ...data, style: itemMeta?.nestedStyle ?? data.style, meta: { start: itemMeta?.nestedStart ?? itemMeta?.start ?? 1, counterType: itemMeta?.counterType ?? meta?.counterType }, items: item.items }, depth + 1) : ""}</li>`;
    })
    .join("");
  return `<${tag}${ordered ? ` start="${start}" type="${counterType}"` : ""}>${content}</${tag}>`;
}

/** Render OutputData without mounting an editable instance: SSR, SEO and print remain readable. */
export function documentToHtml(
  document: EditorDocument,
  headingOffset = 0,
): string {
  const html = document.blocks
    .map((block) => {
      const data = block.data as Record<string, unknown>;
      switch (block.type) {
        case "paragraph":
          return `<p>${cleanHtml(string(data.text), true)}</p>`;
        case "header": {
          const level = Math.min(
            6,
            Math.max(1, integer(data.level, 2) + headingOffset),
          );
          return `<h${level}>${cleanHtml(string(data.text), true)}</h${level}>`;
        }
        case "list":
          return renderList(data);
        case "quote":
          return `<blockquote>${cleanHtml(string(data.text))}${data.caption ? `<p>${cleanHtml(string(data.caption), true)}</p>` : ""}</blockquote>`;
        case "code":
          return `<pre><code>${escapeHtml(string(data.code))}</code></pre>`;
        case "delimiter":
          return "<hr>";
        case "table": {
          const rows = Array.isArray(data.content) ? data.content : [];
          return `<table>${rows
            .map((row: unknown, index: number) => {
              const cell = data.withHeadings && index === 0 ? "th" : "td";
              return `<tr>${(Array.isArray(row) ? row : []).map((value: unknown) => `<${cell}>${cleanHtml(string(value), true)}</${cell}>`).join("")}</tr>`;
            })
            .join("")}</table>`;
        }
        case "image": {
          const file = data.file as Record<string, unknown> | undefined;
          return `<figure><img src="${escapeHtml(string(file?.url ?? data.url))}" alt="${escapeHtml(sanitizeHtml(string(data.caption), { allowedTags: [], allowedAttributes: {} }))}">${data.caption ? `<figcaption>${cleanHtml(string(data.caption), true)}</figcaption>` : ""}</figure>`;
        }
        default:
          return `<pre>${escapeHtml(JSON.stringify(data))}</pre>`;
      }
    })
    .join("\n");
  return cleanHtml(html);
}
