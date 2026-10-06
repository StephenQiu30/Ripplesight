"use client";
import { useEffect, useState, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { marked } from "marked";
import { toast } from "sonner";
import * as UI from "@/components/ui/content";
import {
  getWorkspaceDocumentDraft,
  saveWorkspaceDocumentDraft,
  publishWorkspaceDocument,
  getWorkspaceDocumentOperation,
  getWorkspaceDocumentHistory,
  getWorkspaceDocument,
} from "@/api/xiangmuwendang";
import { useIdentitySession } from "@/components/auth/session-context";
import { cleanHtml } from "@/components/editor/content";
import {
  DocumentEditor,
  type DocumentEditorHandle,
} from "@/components/ui/document-editor";
import { DocumentPreview } from "@/components/ui/workspace-markdown";
import { Button } from "@/components/ui/button";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import { Field, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageState } from "@/components/system/page-state";
import { ApiRequestError } from "@/request";
import { Input } from "@/components/ui/input";
import { documentUrl, documentTypes } from "./catalog";

export function DocumentWorkspace({
  doc,
  catalog,
  children,
  nonce,
}: {
  doc: HotKeyAPI.WorkspaceDocumentView;
  catalog: HotKeyAPI.WorkspaceCatalogView;
  children: ReactNode;
  nonce?: string;
}) {
  const router = useRouter();
  const user = useIdentitySession()?.user.id;
  const [initialOwner] = useState(user);
  const editor = useRef<DocumentEditorHandle>(null);
  const [editing, setEditing] = useState(false);
  const [mode, setMode] = useState("rich");
  const [draft, setDraft] = useState<HotKeyAPI.WorkspaceDraftView | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [blocked, setBlocked] = useState(false);
  const [unknownOperation, setUnknownOperation] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<
    "publish" | "sync" | "restore" | "replace" | null
  >(null);
  const [versions, setVersions] = useState<HotKeyAPI.WorkspaceHistoryItem[]>(
    [],
  );
  const [restoreVersion, setRestoreVersion] = useState("");
  const [replacementPath, setReplacementPath] = useState("");
  const dirty = editing && !!draft && markdown !== draft.markdown;
  useEffect(() => {
    if (editing || blocked || !user || user !== initialOwner) return;
    let frame = 0;
    const locate = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        let anchor: string;
        try {
          anchor = decodeURIComponent(window.location.hash.slice(1));
        } catch {
          return;
        }
        if (
          !anchor ||
          !doc.sections.some((section) => section.anchor === anchor)
        )
          return;
        const target = document.getElementById(anchor);
        target?.scrollIntoView({ block: "start", behavior: "instant" });
        target?.focus({ preventScroll: true });
      });
    };
    // BasicLayout resets its own scroll container on route changes. Locate
    // the chapter after that effect, also when opening a search citation.
    locate();
    window.addEventListener("hashchange", locate);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", locate);
    };
  }, [doc, editing, blocked, user, initialOwner]);
  useEffect(() => {
    const warning = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
      }
    };
    window.addEventListener("beforeunload", warning);
    return () => window.removeEventListener("beforeunload", warning);
  }, [dirty]);
  useEffect(() => {
    if (!editing || !draft) return;
    const guard = (event: MouseEvent) => {
      const target =
        event.target instanceof Element ? event.target.closest("a") : null;
      const href = target?.getAttribute("href");
      if (
        !href ||
        href.startsWith("#") ||
        target?.getAttribute("target") === "_blank" ||
        event.metaKey ||
        event.ctrlKey
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      void (async () => {
        const value =
          mode === "rich" && editor.current
            ? await editor.current.read()
            : markdown;
        setMarkdown(value);
        if (
          value !== draft.markdown &&
          !window.confirm("仍有未保存修改，确认离开此文档？")
        )
          return;
        window.location.assign(href);
      })();
    };
    document.addEventListener("click", guard, true);
    return () => document.removeEventListener("click", guard, true);
  }, [editing, draft, markdown, mode]);
  async function failure(value: unknown) {
    setError(value);
    if (
      value instanceof ApiRequestError &&
      value.code === "workspace_version_conflict"
    ) {
      try {
        const fresh = await getWorkspaceDocumentDraft({
          path: doc.path,
        });
        setDraft({ ...fresh, conflicted: true });
        setMode("diff");
      } catch (e) {
        if (e instanceof ApiRequestError && [401, 403].includes(e.status ?? 0))
          setBlocked(true);
      }
    }
    if (
      value instanceof ApiRequestError &&
      [401, 403].includes(value.status ?? 0)
    ) {
      setBlocked(true);
      setDraft(null);
      setMarkdown("");
      setEditing(false);
    }
    toast.error(
      value instanceof ApiRequestError
        ? value.message
        : "操作失败，请保留修改后重试。",
    );
  }
  async function edit() {
    setBusy(true);
    try {
      const value = await getWorkspaceDocumentDraft({
        path: doc.path,
        snapshot_id: doc.snapshot_id,
      });
      setDraft(value);
      setMarkdown(value.markdown);
      setEditing(true);
      setError(null);
    } catch (e) {
      await failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!draft) return;
    setBusy(true);
    const operation = crypto.randomUUID();
    try {
      const current =
        mode === "rich" && editor.current
          ? await editor.current.read()
          : markdown;
      setMarkdown(current);
      const value = await saveWorkspaceDocumentDraft({
        path: doc.path,
        snapshot_id: draft.snapshot_id,
        source_hash: draft.source_hash,
        draft_revision: draft.revision,
        operation_id: operation,
        markdown: current,
      });
      setDraft(value);
      setError(null);
      toast.success("草稿已保存，发布版本未改变。");
    } catch (e) {
      if (!(e instanceof ApiRequestError) || e.kind !== "http")
        setUnknownOperation(operation);
      await failure(e);
    } finally {
      setBusy(false);
    }
  }
  async function published(value: HotKeyAPI.WorkspaceOperationView) {
    if (value.status === "published" && value.snapshot_id) {
      setEditing(false);
      setDraft(null);
      setMarkdown("");
      setUnknownOperation(null);
      toast.success("文档已发布到本地版本。");
      router.replace(
        documentUrl(value.published_path ?? doc.path, value.snapshot_id),
      );
      router.refresh();
    } else if (value.status === "saved" && value.draft) {
      setDraft(value.draft);
      setUnknownOperation(null);
      toast.success("已核对草稿保存结果。");
    } else if (value.status === "failed") {
      setUnknownOperation(null);
      toast.error("发布未完成，草稿与上一版本已保留。");
    } else {
      setUnknownOperation(value.operation_id);
      toast.info("操作尚未完成，请核对结果。");
    }
  }
  async function publish() {
    if (!draft || !confirmAction) return;
    const operation = crypto.randomUUID();
    setBusy(true);
    setConfirmAction(null);
    try {
      await published(
        await publishWorkspaceDocument({
          action: confirmAction,
          path: doc.path,
          snapshot_id: draft.snapshot_id,
          source_hash:
            confirmAction === "sync"
              ? (draft.current_source_hash ?? draft.source_hash)
              : draft.source_hash,
          replacement_path:
            confirmAction === "replace" ? replacementPath : undefined,
          draft_revision: draft.revision,
          operation_id: operation,
          restore_snapshot_id:
            confirmAction === "restore" ? restoreVersion : undefined,
        }),
      );
    } catch (e) {
      if (!(e instanceof ApiRequestError) || e.kind !== "http")
        setUnknownOperation(operation);
      await failure(e);
    } finally {
      setBusy(false);
    }
  }
  if (!user || user !== initialOwner || blocked)
    return (
      <PageState
        eyebrow="项目文档"
        title="文档访问已结束"
        description="请重新登录或确认文档权限。"
      />
    );
  return (
    <UI.Content layout="stack">
      <UI.Content layout="row">
        <Button variant="ghost" asChild>
          <Link href="/workspace/docs">返回目录</Link>
        </Button>
        <Badge variant="secondary">{documentTypes[doc.type] ?? doc.type}</Badge>
        {doc.status ? <Badge variant="outline">{doc.status}</Badge> : null}
      </UI.Content>
      <UI.Heading level={1}>{doc.title}</UI.Heading>
      <UI.Text tone="muted">
        更新 {doc.updated} · 来源 {doc.source_path} · 版本{" "}
        {doc.source_revision.slice(0, 8)}
      </UI.Text>
      <UI.Content layout="row">
        <Button variant="outline" asChild>
          <UI.TextLink
            href={`/api/workspace/documents/raw?path=${encodeURIComponent(doc.path)}&snapshot_id=${doc.snapshot_id}${doc.status === "废弃" ? "&history=true" : ""}`}
          >
            Markdown 原文
          </UI.TextLink>
        </Button>
        {catalog.can_write && doc.status !== "废弃" && !editing ? (
          <Button onClick={() => void edit()} disabled={busy}>
            编辑文档
          </Button>
        ) : null}
        <Button
          variant="ghost"
          onClick={async () => {
            try {
              const value = await getWorkspaceDocumentHistory({
                path: doc.path,
              });
              setVersions(value.items);
            } catch (e) {
              await failure(e);
            }
          }}
        >
          版本历史
        </Button>
      </UI.Content>
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>操作未完成</AlertTitle>
          <AlertDescription>
            {error instanceof ApiRequestError
              ? error.message
              : "请核对操作结果后继续。"}
          </AlertDescription>
        </Alert>
      ) : null}
      {unknownOperation ? (
        <Alert>
          <AlertTitle>发布结果待核对</AlertTitle>
          <AlertDescription>
            <UI.Text>操作 {unknownOperation}</UI.Text>
            <Button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  await published(
                    await getWorkspaceDocumentOperation({
                      operation_id: unknownOperation,
                    }),
                  );
                } catch (e) {
                  await failure(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              核对操作结果
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {versions.length ? (
        <UI.Content layout="row">
          <Select value={restoreVersion} onValueChange={setRestoreVersion}>
            <SelectTrigger aria-label="历史版本">
              <SelectValue placeholder="选择历史版本" />
            </SelectTrigger>
            <SelectContent>
              {versions.map((value) => (
                <SelectItem key={value.snapshot_id} value={value.snapshot_id}>
                  {value.source_revision.slice(0, 8)} ·{" "}
                  {value.snapshot_id.slice(0, 8)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {restoreVersion && catalog.can_write && doc.status !== "废弃" ? (
            <Button
              variant="outline"
              onClick={async () => {
                try {
                  const value = await getWorkspaceDocument({
                    path: doc.path,
                    snapshot_id: restoreVersion,
                    history: true,
                  });
                  if (!editing) await edit();
                  setMode("source");
                  setMarkdown(value.markdown);
                } catch (e) {
                  await failure(e);
                }
              }}
            >
              加载为草稿
            </Button>
          ) : null}
        </UI.Content>
      ) : null}
      {editing && draft ? (
        <>
          {draft.conflicted ? (
            <Alert>
              <AlertTitle>来源已被修改</AlertTitle>
              <AlertDescription>
                草稿和本地来源均已保留。请对比后合并，再保存。
              </AlertDescription>
            </Alert>
          ) : null}
          <UI.Content layout="row">
            {[
              ["rich", "富文本"],
              ["source", "Markdown 原文"],
              ["preview", "预览"],
              ["diff", "对比差异"],
            ].map(([value, label]) => (
              <Button
                key={value}
                variant={mode === value ? "secondary" : "ghost"}
                onClick={async () => {
                  if (mode === "rich" && editor.current)
                    setMarkdown(await editor.current.read());
                  setMode(value);
                }}
                disabled={busy}
              >
                {label}
              </Button>
            ))}
          </UI.Content>
          {mode === "rich" ? (
            <DocumentEditor
              ref={editor}
              key={`${doc.path}-${draft.revision}-${mode}`}
              markdown={markdown}
              nonce={nonce}
              onChange={setMarkdown}
            />
          ) : null}
          {mode === "source" ? (
            <Field>
              <FieldLabel htmlFor="document-markdown">
                Markdown 文档与元数据
              </FieldLabel>
              <Textarea
                id="document-markdown"
                className="min-h-96 font-mono"
                value={markdown}
                onChange={(e) => setMarkdown(e.target.value)}
                disabled={busy}
              />
            </Field>
          ) : null}
          {mode === "preview" ? (
            <DocumentPreview
              html={cleanHtml(
                String(
                  marked.parse(
                    markdown.replace(
                      /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/,
                      "",
                    ),
                  ),
                ),
              )}
            />
          ) : null}
          {mode === "diff" ? (
            <UI.Content className="grid gap-4 lg:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="source-original">本地来源</FieldLabel>
                <Textarea
                  id="source-original"
                  value={draft.source_markdown ?? draft.base_markdown}
                  readOnly
                  className="min-h-96 font-mono"
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="source-draft">当前草稿</FieldLabel>
                <Textarea
                  id="source-draft"
                  value={markdown}
                  readOnly
                  className="min-h-96 font-mono"
                />
              </Field>
            </UI.Content>
          ) : null}
          {draft.conflicted && draft.markdown !== markdown ? (
            <Field>
              <FieldLabel htmlFor="competing-draft">已保存草稿</FieldLabel>
              <Textarea
                id="competing-draft"
                value={draft.markdown}
                readOnly
                className="min-h-48 font-mono"
              />
            </Field>
          ) : null}
          {draft.conflicted ? (
            <Button
              variant="outline"
              onClick={() =>
                setDraft({
                  ...draft,
                  source_hash: draft.current_source_hash ?? draft.source_hash,
                  conflicted: false,
                })
              }
            >
              已对比并合并来源
            </Button>
          ) : null}
          {doc.type === "decision" && catalog.can_publish ? (
            <Field>
              <FieldLabel htmlFor="replacement-path">
                替代决策路径（使用新的两位编号）
              </FieldLabel>
              <Input
                id="replacement-path"
                value={replacementPath}
                onChange={(e) => setReplacementPath(e.target.value)}
                placeholder="decisions/12-新的技术决策.md"
              />
              <Button
                disabled={
                  busy ||
                  dirty ||
                  draft.revision === 0 ||
                  draft.conflicted ||
                  !!unknownOperation ||
                  !replacementPath
                }
                onClick={() => setConfirmAction("replace")}
              >
                发布替代决策
              </Button>
              <UI.Text tone="muted">
                将草稿作为新决策发布，旧记录标为废弃并保留关联。请在原文中填写新的标题、日期与替代原因。
              </UI.Text>
            </Field>
          ) : null}
          <UI.Content layout="row">
            <Button
              onClick={() => void save()}
              disabled={busy || !!unknownOperation || draft.conflicted}
            >
              保存草稿
            </Button>
            {catalog.can_publish ? (
              <Button
                onClick={() => setConfirmAction("publish")}
                disabled={
                  busy ||
                  dirty ||
                  draft.revision === 0 ||
                  draft.conflicted ||
                  !!unknownOperation
                }
              >
                {doc.type === "decision" ? "发布相同决策" : "确认发布"}
              </Button>
            ) : null}
            {catalog.can_publish ? (
              <Button
                variant="outline"
                onClick={() => setConfirmAction("sync")}
                disabled={busy || dirty || !!unknownOperation}
              >
                发布本地来源修改
              </Button>
            ) : null}
            <Button
              variant="ghost"
              onClick={async () => {
                const current =
                  mode === "rich" && editor.current
                    ? await editor.current.read()
                    : markdown;
                setMarkdown(current);
                if (
                  current === draft?.markdown ||
                  window.confirm("仍有未保存修改，确认离开编辑？")
                )
                  setEditing(false);
              }}
              disabled={busy}
            >
              结束编辑
            </Button>
          </UI.Content>
        </>
      ) : (
        <UI.Content className="grid gap-6 lg:grid-cols-4">
          <UI.Content
            as="aside"
            className="lg:col-span-1"
            aria-label="章节目录"
          >
            <Collapsible defaultOpen>
              <CollapsibleTrigger asChild>
                <Button variant="ghost" className="w-full justify-between">
                  章节目录
                  <ChevronDownIcon aria-hidden="true" />
                </Button>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <UI.ContentList>
                  {doc.sections.map((section) => (
                    <UI.ContentListItem key={section.anchor}>
                      <UI.TextLink href={`#${section.anchor}`}>
                        {section.title}
                      </UI.TextLink>
                    </UI.ContentListItem>
                  ))}
                </UI.ContentList>
              </CollapsibleContent>
            </Collapsible>
            {doc.related.length ? <UI.Text>相关文档</UI.Text> : null}
            {doc.related.map((path) => (
              <UI.Text key={path}>
                <Link href={documentUrl(path, doc.snapshot_id, true)}>
                  {catalog.documents.find((item) => item.path === path)
                    ?.title ?? path}
                </Link>
              </UI.Text>
            ))}
          </UI.Content>
          <UI.Content className="min-w-0 lg:col-span-3">{children}</UI.Content>
        </UI.Content>
      )}
      <AlertDialog
        open={!!confirmAction}
        onOpenChange={(open) => {
          if (!open) setConfirmAction(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认发布到本地知识库？</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmAction === "replace"
                ? "将当前草稿发布为新决策，旧决策标为废弃并建立替代关联。"
                : ""}
              校验文档后保存本地 Git
              历史并切换读取版本。不会推送远端；失败时保留草稿和上一版本。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <Button onClick={() => void publish()} disabled={busy}>
              确认发布
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </UI.Content>
  );
}
