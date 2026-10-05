import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

// Semantic content completes the project's shadcn UI layer. Native elements live
// here so pages compose components without losing HTML/accessibility behavior.
const headingVariants = cva("tracking-tight", {
  variants: {
    level: {
      1: "text-3xl font-medium",
      2: "text-xl font-medium",
      3: "text-lg font-medium",
      4: "text-base font-medium",
      5: "text-sm font-medium",
      6: "text-sm font-medium",
    },
  },
});
export function Heading({
  level = 2,
  className,
  ...props
}: React.ComponentProps<"h1"> & { level?: 1 | 2 | 3 | 4 | 5 | 6 }) {
  return React.createElement(`h${level}`, {
    "data-slot": "heading",
    ...props,
    className: cn(headingVariants({ level }), className),
  });
}
const textVariants = cva("", {
  variants: {
    tone: {
      default: "",
      muted: "text-muted-foreground",
      destructive: "text-destructive",
    },
    size: { inherit: "", sm: "text-sm", xs: "text-xs" },
  },
  defaultVariants: { tone: "default", size: "inherit" },
});
export function Text({
  as = "p",
  tone,
  size,
  className,
  ...props
}: React.ComponentProps<"p"> &
  VariantProps<typeof textVariants> & { as?: "p" | "span" | "strong" }) {
  return React.createElement(as, {
    "data-slot": "text",
    ...props,
    className: cn(textVariants({ tone, size }), className),
  });
}
type ContentElement =
  | "div"
  | "section"
  | "article"
  | "aside"
  | "header"
  | "footer"
  | "main"
  | "figure"
  | "figcaption"
  | "dl"
  | "dt"
  | "dd";
const contentVariants = cva("", {
  variants: {
    layout: {
      flow: "",
      stack: "flex flex-col gap-4",
      row: "flex flex-wrap items-center gap-2",
      grid: "grid gap-4",
    },
  },
  defaultVariants: { layout: "flow" },
});
export function Content({
  as = "div",
  layout,
  className,
  ...props
}: React.HTMLAttributes<HTMLElement> &
  VariantProps<typeof contentVariants> & {
    as?: ContentElement;
    ref?: React.Ref<HTMLElement>;
  }) {
  return React.createElement(as, {
    "data-slot": "content",
    ...props,
    className: cn(contentVariants({ layout }), className),
  });
}
export function ContentList({
  ordered = false,
  className,
  ...props
}: React.ComponentProps<"ul"> & { ordered?: boolean }) {
  return React.createElement(ordered ? "ol" : "ul", {
    "data-slot": "content-list",
    ...props,
    className: cn(className),
  });
}
export function ContentListItem(props: React.ComponentProps<"li">) {
  return <li data-slot="content-list-item" {...props} />;
}
export function CodeBlock({
  className,
  ...props
}: React.ComponentProps<"pre">) {
  return (
    <pre
      data-slot="code-block"
      className={cn("max-w-full overflow-x-auto", className)}
      {...props}
    />
  );
}
export function InlineCode({
  className,
  ...props
}: React.ComponentProps<"code">) {
  return (
    <code
      data-slot="inline-code"
      className={cn("font-mono", className)}
      {...props}
    />
  );
}
export function Quote({
  className,
  ...props
}: React.ComponentProps<"blockquote">) {
  return (
    <blockquote
      data-slot="quote"
      className={cn("border-l-2 pl-4", className)}
      {...props}
    />
  );
}
export function TextLink({ className, ...props }: React.ComponentProps<"a">) {
  return (
    <a
      data-slot="text-link"
      className={cn(
        "focus-visible:outline-ring underline-offset-4 hover:underline",
        className,
      )}
      {...props}
    />
  );
}
export function Timestamp(props: React.ComponentProps<"time">) {
  return <time data-slot="timestamp" {...props} />;
}
export function TextBreak(props: React.ComponentProps<"br">) {
  return <br {...props} />;
}

// Preserve native submit, validation, autofill, keyboard and download/media
// semantics. These primitives do not replace business state or event handlers.
export function Form(props: React.ComponentProps<"form">) {
  return <form data-slot="form" {...props} />;
}
export function VideoPlayer(props: React.ComponentProps<"video">) {
  return <video data-slot="video-player" {...props} />;
}
export function AudioPlayer(props: React.ComponentProps<"audio">) {
  return <audio data-slot="audio-player" {...props} />;
}
export function DocumentRoot(props: React.ComponentProps<"html">) {
  return <html {...props} />;
}
export function DocumentBody(props: React.ComponentProps<"body">) {
  return <body {...props} />;
}
