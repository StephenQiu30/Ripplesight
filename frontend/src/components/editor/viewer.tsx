import * as UI from "@/components/ui/content";
import { cn } from "@/lib/utils";
import {
  cleanHtml,
  documentToHtml,
  markdownToDocument,
  textToDocument,
  type ContentCitation,
  type ContentFormat,
  type ContentValue,
} from "./content";

export type ViewerProps = {
  value: ContentValue;
  format?: ContentFormat;
  citations?: readonly ContentCitation[];
  headingOffset?: number;
  className?: string;
};

export function Viewer({
  value,
  format = "markdown",
  citations,
  headingOffset = 0,
  className,
}: ViewerProps) {
  const html =
    typeof value !== "string"
      ? documentToHtml(value, headingOffset)
      : format === "html"
        ? cleanHtml(value)
        : documentToHtml(
            format === "text"
              ? textToDocument(value)
              : markdownToDocument(value, citations),
            headingOffset,
          );
  return (
    <UI.Content
      data-slot="viewer"
      className={cn("rich-content min-w-0 break-words", className)}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
