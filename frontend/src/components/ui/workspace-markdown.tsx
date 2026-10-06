import type { ComponentProps, ReactNode } from "react";
import type Link from "next/link";
import type { ImageProps } from "next/image";
import * as UI from "@/components/ui/content";

export function safeDocumentHref(
  href: string | undefined,
  snapshot: string,
  history = false,
) {
  if (!href) return undefined;
  if (href.startsWith("workspace-attachment:")) {
    const id = href.slice("workspace-attachment:".length).split(/[?#]/)[0];
    return /^[a-f0-9]{64}$/.test(id)
      ? `/api/workspace/documents/attachment?attachment_id=${id}&snapshot_id=${snapshot}${history ? "&history=true" : ""}`
      : undefined;
  }
  if (href.startsWith("/workspace/docs/") || href.startsWith("#")) {
    const [base, anchor] = href.split("#");
    return base
      ? `${base.endsWith(".md") ? base : base + ".md"}?snapshot=${snapshot}${history ? "&history=true" : ""}${anchor ? `#${anchor}` : ""}`
      : href;
  }
  return /^(https?:\/\/|mailto:)/i.test(href) ? href : undefined;
}

export function documentComponents(snapshot: string, history = false) {
  const heading = (level: 1 | 2 | 3 | 4 | 5 | 6) =>
    function Heading(props: ComponentProps<"h1">) {
      return <UI.Heading {...props} level={level} tabIndex={-1} />;
    };
  return {
    Mermaid: ({ chart }: { chart: string }) => (
      <pre aria-label="Mermaid 图表源代码">
        <code className="language-mermaid">{chart}</code>
      </pre>
    ),
    h1: heading(1),
    h2: heading(2),
    h3: heading(3),
    h4: heading(4),
    h5: heading(5),
    h6: heading(6),
    a: ({
      href,
      children,
      ...props
    }: Omit<ComponentProps<typeof Link>, "href"> & {
      href?: ComponentProps<typeof Link>["href"];
    }) => (
      <UI.TextLink
        {...props}
        href={safeDocumentHref(
          typeof href === "string" ? href : undefined,
          snapshot,
          history,
        )}
      >
        {children}
      </UI.TextLink>
    ),
    img: ({ src, alt }: ImageProps) => {
      const value =
        typeof src === "string"
          ? safeDocumentHref(src, snapshot, history)
          : undefined;
      // Only same-origin authorized attachments are rendered as media.
      return value?.startsWith("/api/workspace/documents/attachment") ? (
        // Authorized media needs the browser session cookie on the original URL.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={value} alt={alt ?? ""} />
      ) : (
        <UI.Text>{alt}</UI.Text>
      );
    },
    p: (props: ComponentProps<"p">) => <UI.Text {...props} />,
    pre: (props: ComponentProps<"pre">) => <pre {...props} />,
    code: (props: ComponentProps<"code">) => <code {...props} />,
    table: (props: ComponentProps<"table">) => (
      <div className="overflow-x-auto">
        <table {...props} />
      </div>
    ),
  };
}

export function DocumentArticle({ children }: { children: ReactNode }) {
  return (
    <article className="rich-content min-w-0" aria-label="文档正文">
      {children}
    </article>
  );
}

export function DocumentPreview({ html }: { html: string }) {
  return (
    <article
      className="rich-content min-w-0"
      aria-label="编辑预览"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
