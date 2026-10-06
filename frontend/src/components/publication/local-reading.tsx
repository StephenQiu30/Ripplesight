"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { BookmarkIcon } from "lucide-react";
import { getSitePublicationItem } from "@/api/gongkaifabu";
import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { PageState } from "@/components/system/page-state";
import { ApiRequestError } from "@/request";
import { categories, publicationTime } from "./reading-format";
import {
  LOCAL_CHANGE,
  savedIds,
  readIds,
  toggleSaved,
  removeSaved,
  markRead,
  localReadingIssue,
} from "./local-state";
export { savedIds } from "./local-state";

export function MarkItemRead({ id }: { id: string }) {
  useEffect(() => {
    let active = true;
    void markRead(id).catch(() => {
      if (active)
        toast.error("本机存储不可用，未保存已读标记。", {
          id: "local-reading-storage",
        });
    });
    return () => {
      active = false;
    };
  }, [id]);
  return null;
}

export function SaveItem({
  id,
  compact = false,
}: {
  id: string;
  compact?: boolean;
}) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const storageFailed = useRef(false);
  useEffect(() => {
    const update = () => {
      try {
        setSaved(savedIds(localStorage).includes(id));
        storageFailed.current = false;
      } catch {
        if (!storageFailed.current)
          toast.error("本机收藏暂时无法读取，请检查本机存储。", {
            id: "local-reading-storage",
          });
        storageFailed.current = true;
      }
    };
    const frame = requestAnimationFrame(update);
    window.addEventListener("storage", update);
    window.addEventListener(LOCAL_CHANGE, update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("storage", update);
      window.removeEventListener(LOCAL_CHANGE, update);
    };
  }, [id]);
  return (
    <>
      <Button
        variant={compact ? "ghost" : "outline"}
        size={compact ? "icon-lg" : "navigation"}
        aria-label={saved ? "取消本机收藏" : "本机收藏"}
        aria-pressed={saved}
        disabled={saving}
        aria-busy={saving}
        onClick={() => {
          setSaving(true);
          void toggleSaved(id)
            .then((value) => {
              setSaved(value);
              toast.success(value ? "已加入本机收藏。" : "已取消本机收藏。");
            })
            .catch(() => toast.error("本机存储不可用，未保存收藏。"))
            .finally(() => setSaving(false));
        }}
      >
        {compact ? (
          <BookmarkIcon
            aria-hidden="true"
            data-icon="inline-start"
            fill={saved ? "currentColor" : "none"}
          />
        ) : saved ? (
          "取消本机收藏"
        ) : (
          "本机收藏"
        )}
      </Button>
    </>
  );
}

export function filterLocalItems(
  items: HotKeyAPI.PublicItemDetailView[],
  category: string,
) {
  return category === "all"
    ? items
    : items.filter((item) =>
        category === "uncategorized"
          ? item.category === null
          : item.category === category,
      );
}

type LocalView = "saved" | "read";
type LocalFailure = { id: string; code: string; status?: number };

export function SavedItems({
  full = false,
  initialCategory = "all",
  initialView = "saved",
  initialPage = 1,
}: {
  full?: boolean;
  initialCategory?: string;
  initialView?: LocalView;
  initialPage?: number;
}) {
  const [items, setItems] = useState<HotKeyAPI.PublicItemDetailView[]>([]);
  const [ids, setIds] = useState<string[]>([]);
  const [read, setRead] = useState<string[]>([]);
  const [page, setPage] = useState(initialPage);
  const [category, setCategory] = useState(initialCategory);
  const [view, setView] = useState<LocalView>(initialView);
  const [busy, setBusy] = useState(true);
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  const [failures, setFailures] = useState<LocalFailure[]>([]);
  const [removing, setRemoving] = useState<string[]>([]);
  const storageFailed = useRef(false);
  const [generation, setGeneration] = useState(0);
  const pageSize = 20;
  const label = view === "read" ? "阅读记录" : "本机收藏";
  const retry = () => setGeneration((old) => old + 1);
  function remember(next: {
    page?: number;
    category?: string;
    view?: LocalView;
  }) {
    if (!full) return;
    const query = new URLSearchParams(window.location.search);
    const values = { page, category, view, ...next };
    for (const [key, value] of Object.entries(values)) {
      if (
        (key === "page" && value === 1) ||
        (key === "category" && value === "all") ||
        (key === "view" && value === "saved")
      )
        query.delete(key);
      else query.set(key, String(value));
    }
    window.history.replaceState(
      null,
      "",
      `/discover/starred${query.size ? `?${query}` : ""}`,
    );
  }
  useEffect(() => {
    const update = () => setGeneration((old) => old + 1);
    window.addEventListener("storage", update);
    window.addEventListener(LOCAL_CHANGE, update);
    return () => {
      window.removeEventListener("storage", update);
      window.removeEventListener(LOCAL_CHANGE, update);
    };
  }, []);
  useEffect(() => {
    let active = true;
    const frame = requestAnimationFrame(() => {
      setBusy(true);
      setItems([]);
      setFailures([]);
      let selected: string[] = [];
      let reading: string[] = [];
      let issue = false;
      try {
        issue = Boolean(localReadingIssue(localStorage));
        if (!issue) {
          reading = readIds(localStorage);
          selected = view === "read" ? reading : savedIds(localStorage);
        }
      } catch {
        issue = true;
      }
      setIds(selected);
      setRead(reading);
      setStorageUnavailable(issue);
      if (issue) {
        setBusy(false);
        if (!storageFailed.current)
          toast.error(
            "本机收藏无法读取。原始数据保留，请检查浏览器存储设置后重新读取。",
            { id: "local-reading-storage" },
          );
        storageFailed.current = true;
        return;
      }
      storageFailed.current = false;
      const lastPage = Math.max(1, Math.ceil(selected.length / pageSize));
      if (page > lastPage) {
        setPage(lastPage);
        if (full) {
          const url = new URL(window.location.href);
          if (lastPage === 1) url.searchParams.delete("page");
          else url.searchParams.set("page", String(lastPage));
          window.history.replaceState(null, "", `${url.pathname}${url.search}`);
        }
        return;
      }
      const current = selected.slice((page - 1) * pageSize, page * pageSize);
      void Promise.allSettled(
        current.map((content_id) => getSitePublicationItem({ content_id })),
      ).then((results) => {
        if (!active) return;
        setItems(
          results.flatMap((result) =>
            result.status === "fulfilled" ? [result.value] : [],
          ),
        );
        setFailures(
          results.flatMap((result, index) => {
            if (result.status === "fulfilled") return [];
            const known =
              result.reason instanceof ApiRequestError ? result.reason : null;
            return [
              {
                id: current[index],
                code: known?.code ?? known?.kind ?? "publication_read_failed",
                status: known?.status,
              },
            ];
          }),
        );
        setBusy(false);
      });
    });
    return () => {
      active = false;
      cancelAnimationFrame(frame);
    };
  }, [page, generation, view, full]);
  const filtered = filterLocalItems(items, category);
  const remove = (id: string) => {
    setRemoving((old) => [...old, id]);
    void removeSaved(id)
      .then(() => toast.success("已取消本机收藏。"))
      .catch(() => toast.error("存储不可用，未删除。"))
      .finally(() => setRemoving((old) => old.filter((entry) => entry !== id)));
  };
  return (
    <UI.Content
      as="section"
      layout="stack"
      aria-label={label}
      className="gap-6"
    >
      <UI.Content layout="stack" className="gap-2">
        <UI.Heading level={2}>
          {full ? (label === "本机收藏" ? "收藏列表" : label) : label}
        </UI.Heading>
        <UI.Text tone="muted" size="sm">
          仅保存在本机浏览器，不跨设备同步。最多 500 篇收藏与 5000
          个已读标记，阅读时重新检查许可。
        </UI.Text>
        {!busy && !storageUnavailable && (
          <UI.Text tone="muted" size="xs">
            共 <UI.InlineCode>{ids.length}</UI.InlineCode>{" "}
            {view === "read" ? "个已读标记" : "篇收藏"}
          </UI.Text>
        )}
      </UI.Content>
      {full && (
        <>
          <UI.Content className="hide-scrollbar max-w-full overflow-x-auto py-1">
            <ToggleGroup
              type="single"
              value={view}
              aria-label="本机记录"
              className="min-w-max"
              onValueChange={(value) => {
                if (value !== "saved" && value !== "read") return;
                setBusy(true);
                setView(value);
                setPage(1);
                remember({ view: value, page: 1 });
              }}
            >
              <ToggleGroupItem value="saved">收藏</ToggleGroupItem>
              <ToggleGroupItem value="read">阅读记录</ToggleGroupItem>
            </ToggleGroup>
          </UI.Content>
          <UI.Content layout="stack" className="gap-2">
            <UI.Text size="sm">本页分类</UI.Text>
            <UI.Content className="hide-scrollbar max-w-full overflow-x-auto py-1">
              <ToggleGroup
                type="single"
                value={category}
                aria-label="本页分类"
                className="min-w-max"
                onValueChange={(value) => {
                  if (value) {
                    setCategory(value);
                    remember({ category: value });
                  }
                }}
              >
                <ToggleGroupItem value="all">全部分类</ToggleGroupItem>
                {categories.map(([key, name]) => (
                  <ToggleGroupItem key={key} value={key}>
                    {name}
                  </ToggleGroupItem>
                ))}
                <ToggleGroupItem value="uncategorized">未分类</ToggleGroupItem>
              </ToggleGroup>
            </UI.Content>
            <UI.Text size="xs" tone="muted">
              分类只筛选当前页已读取的资讯；分页按本机编号顺序，每页重新检查许可。
            </UI.Text>
          </UI.Content>
        </>
      )}
      {busy ? (
        <PageState
          state="loading"
          eyebrow={label}
          title="正在读取当前公开材料…"
          description="正在检查本机编号与当前许可。"
        />
      ) : storageUnavailable ? (
        <Alert aria-label="本机收藏暂不可读">
          <AlertTitle>本机收藏暂不可读</AlertTitle>
          <AlertDescription>
            浏览器存储不可用或记录损坏。已有数据未覆盖，请检查存储设置后重新读取。
          </AlertDescription>
        </Alert>
      ) : (
        <>
          {failures.length > 0 && (
            <PageState
              state="error"
              eyebrow={label}
              title="部分材料暂不可读"
              description={`${failures.length} 篇材料已撤回、许可变化或暂时无法读取。其他材料仍可阅读，编号会保留。`}
              errorCode={failures[0].code}
              httpStatus={failures[0].status}
              action={
                <Button variant="outline" size="navigation" onClick={retry}>
                  重新读取
                </Button>
              }
            />
          )}
          {filtered.length ? (
            <ItemGroup className="gap-0">
              {filtered.map((item) => (
                <Fragment key={item.id}>
                  <Separator />
                  <Item role="listitem" className="items-start gap-3 px-0 py-5">
                    <ItemContent className="min-w-0 gap-3">
                      <UI.Content layout="row">
                        <Badge variant="secondary">
                          {categories.find(
                            ([key]) => key === item.category,
                          )?.[1] ?? "未分类"}
                        </Badge>
                        <UI.Text size="xs" tone="muted">
                          {item.source.name}
                        </UI.Text>
                        {read.includes(item.id) && (
                          <Badge variant="outline">已读</Badge>
                        )}
                      </UI.Content>
                      <ItemTitle className="line-clamp-none break-words">
                        <UI.Heading level={3}>
                          <UI.TextLink href={item.reading_url}>
                            {item.title}
                          </UI.TextLink>
                        </UI.Heading>
                      </ItemTitle>
                      {item.summary && (
                        <ItemDescription className="line-clamp-none break-words">
                          {item.summary}
                        </ItemDescription>
                      )}
                      <UI.Text tone="muted" size="xs">
                        {item.published_at ? "发布于 " : "发现于 "}
                        <UI.InlineCode>
                          {publicationTime(item.timeline_at)}
                        </UI.InlineCode>
                      </UI.Text>
                      <ItemActions className="flex-wrap">
                        <Button asChild variant="ghost" size="feed">
                          <Link
                            href={item.original_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            来源原文
                          </Link>
                        </Button>
                        {full && view === "saved" && (
                          <Button
                            variant="ghost"
                            size="feed"
                            disabled={removing.includes(item.id)}
                            aria-label={`取消收藏：${item.title}`}
                            onClick={() => remove(item.id)}
                          >
                            取消收藏
                          </Button>
                        )}
                      </ItemActions>
                    </ItemContent>
                  </Item>
                </Fragment>
              ))}
              <Separator />
            </ItemGroup>
          ) : (
            failures.length === 0 && (
              <PageState
                state="empty"
                eyebrow={label}
                title={
                  ids.length
                    ? "本页没有符合分类的资讯"
                    : view === "read"
                      ? "还没有阅读记录。"
                      : "还没有收藏。"
                }
                description={
                  ids.length
                    ? "选择全部分类或继续翻页。"
                    : view === "read"
                      ? "打开公开资讯后，本机记录会出现在这里。"
                      : "在公开资讯旁点击收藏，即可在这里继续阅读。"
                }
                action={
                  ids.length ? (
                    <Button
                      variant="outline"
                      onClick={() => {
                        setCategory("all");
                        remember({ category: "all" });
                      }}
                    >
                      全部分类
                    </Button>
                  ) : (
                    <Button asChild variant="outline">
                      <Link href="/discover">去探索资讯</Link>
                    </Button>
                  )
                }
              />
            )
          )}
          {full && view === "saved" && failures.length > 0 && (
            <ItemGroup>
              {failures.map((failure) => (
                <Item
                  key={failure.id}
                  role="listitem"
                  className="items-start px-0"
                >
                  <ItemContent className="min-w-0 gap-2">
                    <UI.Text size="sm" tone="muted" className="break-all">
                      暂时不可读取 · {failure.id}
                    </UI.Text>
                    <UI.Text size="xs">
                      <UI.InlineCode>
                        {[failure.code, failure.status]
                          .filter(Boolean)
                          .join(" · ")}
                      </UI.InlineCode>
                    </UI.Text>
                  </ItemContent>
                  <ItemActions>
                    <Button
                      variant="ghost"
                      size="navigation"
                      disabled={removing.includes(failure.id)}
                      aria-label={`移除不可读收藏：${failure.id}`}
                      onClick={() => remove(failure.id)}
                    >
                      移除
                    </Button>
                  </ItemActions>
                </Item>
              ))}
            </ItemGroup>
          )}
        </>
      )}
      {full ? (
        <UI.Content
          role="navigation"
          aria-label={`${label}分页`}
          className="flex flex-wrap items-center gap-3"
        >
          {!storageUnavailable && (
            <>
              {page > 1 && (
                <Button
                  variant="outline"
                  size="navigation"
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    setPage(page - 1);
                    remember({ page: page - 1 });
                  }}
                >
                  上一页
                </Button>
              )}
              <UI.Text size="sm">
                <UI.InlineCode>
                  第 {page} / {Math.max(1, Math.ceil(ids.length / pageSize))} 页
                </UI.InlineCode>
              </UI.Text>
              {page * pageSize < ids.length && (
                <Button
                  variant="outline"
                  size="navigation"
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    setPage(page + 1);
                    remember({ page: page + 1 });
                  }}
                >
                  下一页
                </Button>
              )}
            </>
          )}
          <Button
            variant="outline"
            size="navigation"
            disabled={busy}
            onClick={retry}
          >
            重新读取
          </Button>
        </UI.Content>
      ) : (
        <Button
          asChild
          variant="outline"
          size="navigation"
          className="self-start"
        >
          <Link href="/discover/starred">查看本机收藏与阅读记录</Link>
        </Button>
      )}
    </UI.Content>
  );
}
