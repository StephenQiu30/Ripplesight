"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import * as UI from "@/components/ui/content";
import {
  listWorkspaceDocuments,
  searchWorkspaceDocuments,
} from "@/api/xiangmuwendang";
import { useIdentitySession } from "@/components/auth/session-context";
import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import { Badge } from "@/components/ui/badge";
import { ApiRequestError } from "@/request";

export const documentTypes: Record<string, string> = {
  prd: "产品需求",
  plan: "执行计划",
  pointer: "项目参考",
  capability: "能力",
  decision: "技术决策",
  record: "验收",
  research: "调研",
  glossary: "术语",
  index: "阅读指南",
};
export function documentUrl(path: string, snapshot: string, history = false) {
  return `/workspace/docs/${path.split("/").map(encodeURIComponent).join("/")}?snapshot=${snapshot}${history ? "&history=true" : ""}`;
}
export function WorkspaceCatalog() {
  const user = useIdentitySession()?.user.id;
  const epoch = useRef(0);
  const searchSequence = useRef(0);
  const [loadedFor, setLoadedFor] = useState<string | undefined>(undefined);
  const [catalog, setCatalog] = useState<HotKeyAPI.WorkspaceCatalogView | null>(
    null,
  );
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [results, setResults] = useState<HotKeyAPI.WorkspaceSearchView | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const [history, setHistory] = useState(false);
  useEffect(() => {
    let active = true;
    epoch.current++;
    searchSequence.current++;
    const controller = new AbortController();
    listWorkspaceDocuments({ history }, { signal: controller.signal })
      .then((value) => {
        if (active) {
          setCatalog(value);
          setLoadedFor(user);
          setError(null);
          setResults(null);
          setBusy(false);
        }
      })
      .catch((error) => {
        if (active) {
          setCatalog(null);
          setError(error);
        }
      });
    return () => {
      active = false;
      // These scalar counters revoke pending requests when the identity leaves.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      epoch.current++;
      // eslint-disable-next-line react-hooks/exhaustive-deps
      searchSequence.current++;
      controller.abort();
    };
  }, [user, retry, history]);
  if (!user)
    return (
      <PageState
        state="forbidden"
        eyebrow="项目知识库"
        title="需要登录"
        description="请登录后读取项目资料。"
      />
    );
  if (error)
    return (
      <PageState
        state={
          error instanceof ApiRequestError && error.status === 403
            ? "forbidden"
            : "error"
        }
        errorCode={error instanceof ApiRequestError ? error.code : undefined}
        httpStatus={error instanceof ApiRequestError ? error.status : undefined}
        eyebrow="项目知识库"
        title={
          error instanceof ApiRequestError && error.status === 403
            ? "没有文档访问权限"
            : "知识库暂不可用"
        }
        description={
          error instanceof ApiRequestError
            ? error.message
            : "读取失败，请重试。"
        }
        action={<Button onClick={() => setRetry(retry + 1)}>重试</Button>}
      />
    );
  if (!catalog || loadedFor !== user)
    return (
      <>
        <UI.Heading level={1} className="sr-only">
          正在读取文档
        </UI.Heading>
        <PageState
          state="loading"
          eyebrow="项目知识库"
          title="正在读取文档"
          description="正在核对项目资料和版本。"
        />
      </>
    );
  const items = catalog.documents.filter((item) => !type || item.type === type);
  return (
    <UI.Content layout="stack">
      <UI.Heading level={1}>项目知识库</UI.Heading>
      <UI.Text tone="muted">
        需求、决策、计划与验收共用一个版本。当前版本{" "}
        {catalog.source_revision.slice(0, 8)}
      </UI.Text>
      <Button
        variant="outline"
        aria-pressed={history}
        onClick={() => {
          setCatalog(null);
          setResults(null);
          setHistory(!history);
        }}
      >
        {history ? "返回生效资料" : "查看历史资料（含废弃）"}
      </Button>
      <UI.Form
        onSubmit={async (event) => {
          event.preventDefault();
          if (!query.trim()) {
            setResults(null);
            return;
          }
          setBusy(true);
          const ownerEpoch = epoch.current,
            sequence = ++searchSequence.current;
          try {
            const value = await searchWorkspaceDocuments({
              query,
              snapshot_id: catalog.snapshot_id,
              history,
            });
            if (
              epoch.current === ownerEpoch &&
              searchSequence.current === sequence
            )
              setResults(value);
          } catch (e) {
            if (
              epoch.current === ownerEpoch &&
              searchSequence.current === sequence
            ) {
              setCatalog(null);
              setResults(null);
              setError(e);
            }
          } finally {
            if (
              epoch.current === ownerEpoch &&
              searchSequence.current === sequence
            )
              setBusy(false);
          }
        }}
      >
        <Field>
          <FieldLabel htmlFor="workspace-query">搜索项目文档</FieldLabel>
          <UI.Content layout="row">
            <Input
              id="workspace-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例如：权限、PRD、发布冲突"
            />
            <Button type="submit" disabled={busy}>
              {busy ? "搜索中" : "搜索"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                searchSequence.current++;
                setBusy(false);
                setQuery("");
                setResults(null);
              }}
            >
              清除
            </Button>
          </UI.Content>
        </Field>
      </UI.Form>
      <UI.Content role="group" layout="row" aria-label="文档分类">
        <Button
          variant={!type ? "secondary" : "ghost"}
          onClick={() => setType("")}
        >
          全部
        </Button>
        {Object.entries(documentTypes).map(([key, label]) => (
          <Button
            key={key}
            variant={type === key ? "secondary" : "ghost"}
            onClick={() => {
              setType(key);
              setResults(null);
            }}
          >
            {label}
          </Button>
        ))}
      </UI.Content>
      {results ? (
        <ItemGroup>
          {results.items.length ? (
            results.items.map((item, index) => (
              <Item key={index} role="listitem">
                <ItemContent>
                  <ItemTitle>
                    <Link
                      href={
                        documentUrl(item.path, results.snapshot_id, history) +
                        (item.anchor ? `#${item.anchor}` : "")
                      }
                    >
                      {item.title} · {item.section_title}
                    </Link>
                  </ItemTitle>
                  <ItemDescription>{item.snippet}</ItemDescription>
                </ItemContent>
              </Item>
            ))
          ) : (
            <Item role="listitem">
              <UI.Text>没有找到相关文档。</UI.Text>
            </Item>
          )}
        </ItemGroup>
      ) : (
        <ItemGroup>
          {items.length ? (
            items.map((item) => (
              <Item key={item.path} role="listitem">
                <ItemContent>
                  <ItemTitle>
                    <Link
                      href={documentUrl(
                        item.path,
                        catalog.snapshot_id,
                        history,
                      )}
                    >
                      {item.title}
                    </Link>
                    <Badge variant="secondary">
                      {documentTypes[item.type] ?? item.type}
                    </Badge>
                    {item.status ? (
                      <Badge variant="outline">{item.status}</Badge>
                    ) : null}
                  </ItemTitle>
                  <ItemDescription>{item.summary}</ItemDescription>
                </ItemContent>
              </Item>
            ))
          ) : (
            <Item role="listitem">
              <UI.Text>此分类暂无文档。</UI.Text>
            </Item>
          )}
        </ItemGroup>
      )}
    </UI.Content>
  );
}
