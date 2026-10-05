"use client";

import type EditorJS from "@editorjs/editorjs";
import {
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { normalizeDocument, type EditorDocument } from "./content";
import { loadEditor, editorI18n } from "./tools";

export type EditorHandle = { save: () => Promise<EditorDocument> };
export type EditorProps = {
  value: EditorDocument;
  onChange?: (value: EditorDocument) => void;
  onReady?: () => void;
  onError?: (error: Error) => void;
  ref?: Ref<EditorHandle>;
  id?: string;
  "aria-labelledby"?: string;
  "aria-label"?: string;
  placeholder?: string;
  readOnly?: boolean;
  className?: string;
};

type Session = {
  instance?: EditorJS;
  ready: Promise<void>;
  queue: Promise<void>;
  disposed: boolean;
  rendering: boolean;
  initialized: boolean;
  failed: boolean;
  fingerprint: string;
  change: number;
};
const fingerprint = (value: EditorDocument) =>
  JSON.stringify(
    (normalizeDocument(value) ?? value).blocks.map(({ type, data }) => ({
      type,
      data,
    })),
  );

export function Editor({
  value,
  onChange,
  onReady,
  onError,
  ref,
  id,
  "aria-labelledby": labelledBy,
  "aria-label": label,
  placeholder = "开始书写，点击 + 添加内容块…",
  readOnly = false,
  className,
}: EditorProps) {
  const holder = useRef<HTMLDivElement>(null);
  const sessionRef = useRef<Session | null>(null);
  const latest = useRef({ value, onChange, onReady, onError });
  useEffect(() => {
    latest.current = { value, onChange, onReady, onError };
  });
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);

  useImperativeHandle(
    ref,
    () => ({
      async save() {
        const session = sessionRef.current;
        if (!session || session.disposed) throw new Error("编辑器尚未就绪。");
        await session.ready;
        await session.queue;
        if (session.disposed || session.failed || !session.instance)
          throw new Error("编辑器已关闭。");
        return session.instance.save();
      },
    }),
    [],
  );

  useEffect(() => {
    const container = holder.current;
    if (!container) return;
    // A dedicated child prevents an old asynchronous instance clearing its successor's DOM.
    const mount = document.createElement("div");
    container.append(mount);
    const session: Session = {
      ready: Promise.resolve(),
      queue: Promise.resolve(),
      disposed: false,
      rendering: false,
      initialized: false,
      failed: false,
      fingerprint: "",
      change: 0,
    };
    sessionRef.current = session;
    const fail = () => {
      if (session.disposed) return;
      session.failed = true;
      setState("error");
      const error = new Error("编辑器暂时无法加载或保存，请重试。");
      if (latest.current.onError) latest.current.onError(error);
      else toast.error(error.message);
    };
    const publishChange = async () => {
      if (session.disposed || session.rendering || !session.initialized) return;
      const change = ++session.change;
      try {
        const document = await session.instance!.save();
        if (session.disposed || session.rendering || change !== session.change)
          return;
        const nextFingerprint = fingerprint(document);
        if (nextFingerprint === session.fingerprint) return;
        session.fingerprint = nextFingerprint;
        latest.current.onChange?.(document);
      } catch {
        fail();
      }
    };
    const immediateChange = () => {
      void publishChange();
    };
    mount.addEventListener("input", immediateChange);
    mount.addEventListener("change", immediateChange);
    const labelFields = () => {
      mount
        .querySelectorAll<HTMLElement>('[contenteditable="true"]')
        .forEach((element) => {
          element.setAttribute("role", "textbox");
          element.setAttribute("aria-multiline", "true");
          if (labelledBy) element.setAttribute("aria-labelledby", labelledBy);
          else if (label) element.setAttribute("aria-label", label);
        });
      mount
        .querySelectorAll<HTMLElement>(
          ".ce-toolbar__plus, .ce-toolbar__settings-btn, .ce-popover-item",
        )
        .forEach((element) => {
          element.setAttribute("role", "button");
          element.tabIndex = 0;
          if (element.matches(".ce-toolbar__plus"))
            element.setAttribute("aria-label", "添加块");
          if (element.matches(".ce-toolbar__settings-btn"))
            element.setAttribute("aria-label", "块设置");
        });
      mount
        .querySelectorAll<HTMLElement>(".ce-popover__items")
        .forEach((element) => {
          element.tabIndex = 0;
          element.setAttribute("role", "group");
          element.setAttribute("aria-label", "工具选项");
        });
    };
    const activateTool = (event: KeyboardEvent) => {
      if (
        !(event.target instanceof HTMLElement) ||
        !event.target.matches(
          ".ce-toolbar__plus, .ce-toolbar__settings-btn, .ce-popover-item",
        )
      )
        return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        event.target.click();
      }
    };
    mount.addEventListener("keydown", activateTool);
    const observer = new MutationObserver((records) => {
      labelFields();
      // Core onChange is debounced; capture content mutations before an immediate route exit.
      if (
        records.some((record) => {
          const target =
            record.target instanceof Element
              ? record.target
              : record.target.parentElement;
          return (
            target?.closest(".ce-block__content") ||
            target?.matches(".codex-editor__redactor")
          );
        })
      )
        void publishChange();
    });
    observer.observe(mount, {
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "checked", "data-checked"],
      subtree: true,
    });
    const initialize = async () => {
      const { EditorJS: Constructor, tools } = await loadEditor();
      if (session.disposed) return;
      const data = normalizeDocument(latest.current.value);
      if (!data) throw new Error("不支持的编辑内容。");
      session.fingerprint = fingerprint(data);
      session.instance = new Constructor({
        holder: mount,
        data,
        tools,
        readOnly,
        placeholder,
        minHeight: 120,
        inlineToolbar: ["bold", "italic", "link", "inlineCode"],
        i18n: editorI18n,
        logLevel: "ERROR" as import("@editorjs/editorjs").LogLevels,
        onChange: publishChange,
      });
      try {
        await session.instance.isReady;
      } catch (error) {
        mount.remove();
        throw error;
      }
      if (session.disposed) return;
      // Value may have changed while the tool chunks were initializing.
      while (!session.disposed) {
        const current = normalizeDocument(latest.current.value);
        if (!current) throw new Error("不支持的编辑内容。");
        if (fingerprint(current) === session.fingerprint) break;
        session.rendering = true;
        try {
          await session.instance.render(current);
          session.fingerprint = fingerprint(current);
        } finally {
          session.rendering = false;
        }
      }
      session.initialized = true;
      labelFields();
      if (!session.disposed) {
        setState("ready");
        latest.current.onReady?.();
      }
    };
    session.ready = initialize();
    void session.ready.catch(fail);
    return () => {
      observer.disconnect();
      mount.removeEventListener("keydown", activateTool);
      mount.removeEventListener("input", immediateChange);
      mount.removeEventListener("change", immediateChange);
      session.disposed = true;
      session.change++;
      if (sessionRef.current === session) sessionRef.current = null;
      // isReady may still be pending; destroy only when the instance has its API.
      void session.ready
        .catch(() => {})
        .then(() => {
          if (session.instance?.destroy) session.instance.destroy();
        })
        .catch(() => {});
      mount.remove();
    };
  }, [attempt, readOnly, placeholder, labelledBy, label]);

  useEffect(() => {
    const session = sessionRef.current;
    if (!session || !session.initialized) return;
    const data = normalizeDocument(value);
    if (!data) {
      latest.current.onError?.(new Error("不支持的编辑内容。"));
      return;
    }
    const nextFingerprint = fingerprint(data);
    // Never re-render an onChange echo: preserve the user's selection and undo state.
    if (nextFingerprint === session.fingerprint) return;
    session.change++;
    session.queue = session.queue
      .then(async () => {
        await session.ready;
        if (
          session.disposed ||
          !session.instance ||
          nextFingerprint === session.fingerprint
        )
          return;
        session.rendering = true;
        try {
          await session.instance.render(data);
          session.fingerprint = nextFingerprint;
        } finally {
          session.rendering = false;
        }
      })
      .catch(() => {
        if (session.disposed) return;
        session.failed = true;
        setState("error");
        const error = new Error("编辑内容更新失败，请重试。");
        if (latest.current.onError) latest.current.onError(error);
        else toast.error(error.message);
      });
  }, [value]);

  return (
    <div data-slot="editor" className={cn("rich-editor min-w-0", className)}>
      {state === "loading" ? (
        <div aria-label="正在加载编辑器" className="flex flex-col gap-3">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-5 w-1/2" />
        </div>
      ) : null}
      {state === "error" ? (
        <Alert>
          <AlertDescription>
            编辑器暂时不可用。
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setState("loading");
                setAttempt((count) => count + 1);
              }}
            >
              重新加载
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      <div
        ref={holder}
        id={id}
        role="group"
        aria-labelledby={labelledBy}
        aria-label={label}
        aria-busy={state === "loading"}
        hidden={state !== "ready"}
      />
    </div>
  );
}
