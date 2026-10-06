"use client";
import {
  useEffect,
  useRef,
  useState,
  useImperativeHandle,
  type Ref,
} from "react";
import type EditorJS from "@editorjs/editorjs";
import type {
  BlockToolConstructorOptions,
  LogLevels,
} from "@editorjs/editorjs";
import {
  sourceBlocks,
  sourceMarkdown,
  type SourceBlock,
} from "@/components/editor/document-source";
import { cleanHtml } from "@/components/editor/content";

class SourceTool {
  private data: SourceBlock;
  private element: HTMLDivElement | HTMLTextAreaElement | null = null;
  static get isReadOnlySupported() {
    return true;
  }
  static get sanitize() {
    // These fields carry authored Markdown. Rendering and edited HTML are
    // sanitized separately; Editor.js must not rewrite the source on save.
    return {
      kind: true,
      raw: true,
      html: true,
      originalHtml: true,
      suffix: true,
    };
  }
  static get toolbox() {
    return { title: "段落", icon: "¶" };
  }
  constructor({ data }: BlockToolConstructorOptions<SourceBlock>) {
    this.data = {
      kind: "paragraph",
      raw: "",
      html: "",
      originalHtml: "",
      suffix: "",
      ...(data as Partial<SourceBlock>),
    };
  }
  render() {
    if (this.data.kind === "raw") {
      const element = document.createElement("textarea");
      element.value = this.data.raw;
      element.rows = Math.min(
        20,
        Math.max(2, this.data.raw.split("\n").length),
      );
      element.setAttribute("aria-label", "保留格式的 Markdown 块");
      element.className =
        "w-full rounded-lg border border-input bg-background p-3 font-mono text-sm";
      this.element = element;
    } else {
      const element = document.createElement("div");
      element.contentEditable = "true";
      element.setAttribute("role", "textbox");
      element.setAttribute(
        "aria-label",
        this.data.kind === "heading" ? "文档标题" : "文档段落",
      );
      element.className =
        this.data.kind === "heading"
          ? "py-2 text-xl font-medium"
          : "py-2 leading-7";
      element.innerHTML = cleanHtml(this.data.html, true);
      this.element = element;
    }
    return this.element;
  }
  save() {
    if (this.element instanceof HTMLTextAreaElement)
      return { ...this.data, raw: this.element.value };
    return {
      ...this.data,
      html: cleanHtml(this.element?.innerHTML ?? "", true),
    };
  }
}

export type DocumentEditorHandle = { read: () => Promise<string> };
export function DocumentEditor({
  markdown,
  nonce,
  onChange,
  ref,
}: {
  markdown: string;
  nonce?: string;
  onChange: (value: string) => void;
  ref?: Ref<DocumentEditorHandle>;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const editor = useRef<EditorJS | undefined>(undefined);
  useImperativeHandle(
    ref,
    () => ({
      read: async () => {
        if (!editor.current) return markdown;
        await editor.current.isReady;
        return sourceMarkdown(await editor.current.save());
      },
    }),
    [markdown],
  );
  const callback = useRef(onChange);
  const [error, setError] = useState(false);
  useEffect(() => {
    callback.current = onChange;
  }, [onChange]);
  useEffect(() => {
    let cancelled = false;
    let instance: EditorJS | undefined;
    let composing = false;
    let sequence = 0;
    const element = holder.current;
    const changed = async () => {
      if (!instance || cancelled || composing) return;
      const current = ++sequence;
      const value = sourceMarkdown(await instance.save());
      if (!cancelled && current === sequence) callback.current(value);
    };
    const start = () => {
      composing = true;
    };
    const end = () => {
      composing = false;
      void changed();
    };
    element?.addEventListener("compositionstart", start);
    element?.addEventListener("compositionend", end);
    void import("@editorjs/editorjs")
      .then(async ({ default: Editor }) => {
        if (cancelled || !element) return;
        instance = new Editor({
          holder: element,
          tools: { source: SourceTool },
          defaultBlock: "source",
          data: sourceBlocks(markdown),
          onChange: changed,
          style: { nonce },
          minHeight: 0,
          // Upstream declares LogLevels as an enum but only exports Editor
          // at runtime from its ESM bundle.
          logLevel: "ERROR" as LogLevels,
        });
        editor.current = instance;
        await instance.isReady;
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
      editor.current = undefined;
      element?.removeEventListener("compositionstart", start);
      element?.removeEventListener("compositionend", end);
      if (instance)
        void instance.isReady.then(() => instance?.destroy()).catch(() => {});
    };
    // A mode switch remounts from the same draft; user edits never recreate Editor.js.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce]);
  return error ? (
    <p role="alert">富文本编辑器无法加载，请切换原文视图继续编辑。</p>
  ) : (
    <div
      ref={holder}
      className="rich-content min-w-0"
      aria-label="富文本文档编辑器"
    />
  );
}
