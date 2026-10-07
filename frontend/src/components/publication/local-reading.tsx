"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { BookmarkIcon, SearchIcon } from "lucide-react";
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
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
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
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const download = useRef<HTMLAnchorElement>(null);
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
  const filtered = filterLocalItems(items, category).filter(
    (item) =>
      !query.trim() ||
      `${item.title} ${item.summary ?? ""} ${item.source.name}`
        .toLocaleLowerCase()
        .includes(query.trim().toLocaleLowerCase()),
  );
  const selectedItems =
    view === "saved" && !busy
      ? filtered.filter((item) => selected.includes(item.id))
      : [];
  function exportItems(values: HotKeyAPI.PublicItemDetailView[]) {
    if (!values.length) return;
    const markdown = [
      `# 知微见澜 · ${label}`,
      ...values.map(
        (item) =>
          `## ${item.title.replaceAll("\n", " ")}\n\n来源：${item.source.name}\n\n${item.original_url}\n\n发布时间 / 发现时间：${item.timeline_at}`,
      ),
    ].join("\n\n");
    const url = URL.createObjectURL(
      new Blob([markdown], { type: "text/markdown;charset=utf-8" }),
    );
    if (download.current) {
      download.current.href = url;
      download.current.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast.success(`已导出 ${values.length} 篇资讯的来源链接。`);
  }
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
      <UI.TextLink
        ref={download}
        download="ripplesight-saved.md"
        className="hidden"
        aria-hidden="true"
        tabIndex={-1}
      >
        下载收藏
      </UI.TextLink>
      <UI.Content className="flex flex-wrap items-center justify-between gap-4">
        <UI.Content layout="stack" className="gap-1">
          <UI.Heading level={2} className={full ? "sr-only" : undefined}>
            {full ? (label === "本机收藏" ? "收藏列表" : label) : label}
          </UI.Heading>
          <UI.Text tone="muted" size="sm">
            {!busy && !storageUnavailable
              ? `共 ${ids.length} ${view === "read" ? "个已读标记" : "篇收藏"} · `
              : ""}
            仅保存在本机浏览器，不跨设备同步。
          </UI.Text>
        </UI.Content>
        {full ? (
          <Field className="w-full md:w-65">
            <FieldLabel htmlFor="saved-search" className="sr-only">
              搜索本页收藏
            </FieldLabel>
            <InputGroup>
              <InputGroupAddon>
                <SearchIcon />
              </InputGroupAddon>
              <InputGroupInput
                id="saved-search"
                type="search"
                placeholder="在本页收藏中搜索"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </InputGroup>
          </Field>
        ) : null}
      </UI.Content>
      <UI.Content className={full ? "reading-columns items-start" : undefined}>
        <UI.Content className="flex min-w-0 flex-col gap-4">
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
                    <ToggleGroupItem value="uncategorized">
                      未分类
                    </ToggleGroupItem>
                  </ToggleGroup>
                </UI.Content>
                <UI.Text size="xs" tone="muted">
                  分类只筛选当前页已读取的资讯；分页按本机编号顺序，每页重新检查许可。
                </UI.Text>
              </UI.Content>
            </>
          )}
          {full && selectedItems.length > 0 ? (
            <Card variant="inverse" size="sm">
              <CardContent className="flex flex-wrap items-center justify-between gap-2">
                <UI.Text size="sm">已选 {selectedItems.length} 项</UI.Text>
                <UI.Content className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => exportItems(selectedItems)}
                  >
                    导出 Markdown
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setSelected([])}
                  >
                    清除选择
                  </Button>
                </UI.Content>
              </CardContent>
            </Card>
          ) : null}
          {busy ? (
            <PageState
              headingLevel={2}
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
                  headingLevel={2}
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
                      <Item
                        role="listitem"
                        className="flex-nowrap items-start gap-4 px-0 py-5"
                      >
                        {full && view === "saved" ? (
                          <Checkbox
                            className="mt-1"
                            aria-label={`选择收藏：${item.title}`}
                            checked={selected.includes(item.id)}
                            onCheckedChange={(checked) =>
                              setSelected((current) =>
                                checked === true
                                  ? [...current, item.id]
                                  : current.filter((id) => id !== item.id),
                              )
                            }
                          />
                        ) : null}
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
                    headingLevel={2}
                    state="empty"
                    eyebrow={label}
                    title={
                      ids.length
                        ? query.trim()
                          ? "本页没有匹配的收藏"
                          : "本页没有符合分类的资讯"
                        : view === "read"
                          ? "还没有阅读记录。"
                          : "还没有收藏。"
                    }
                    description={
                      ids.length
                        ? query.trim()
                          ? "尝试其他关键词，或清除搜索条件。"
                          : "选择全部分类或继续翻页。"
                        : view === "read"
                          ? "打开公开资讯后，本机记录会出现在这里。"
                          : "在公开资讯旁点击收藏，即可在这里继续阅读。"
                    }
                    action={
                      ids.length ? (
                        <Button
                          variant="outline"
                          onClick={() => {
                            setQuery("");
                            setCategory("all");
                            remember({ category: "all" });
                          }}
                        >
                          {query.trim() ? "清除筛选" : "全部分类"}
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
                      第 {page} /{" "}
                      {Math.max(1, Math.ceil(ids.length / pageSize))} 页
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
        {full ? (
          <UI.Content
            as="aside"
            aria-label="收藏说明"
            className="flex min-w-0 flex-col gap-8"
          >
            <Card variant="muted">
              <CardHeader>
                <CardTitle>导出与知识库</CardTitle>
                <CardDescription>
                  将本页可读收藏的标题、原文链接与时间导出为
                  Markdown，方便放进自己的笔记库。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  variant="secondary"
                  disabled={busy || !filtered.length}
                  onClick={() => exportItems(filtered)}
                >
                  导出本页
                </Button>
              </CardContent>
            </Card>
            <UI.Text tone="muted" size="xs">
              最多保存 500 篇收藏与 5000
              个已读标记。每次阅读重新检查公开许可；暂不可读的编号会保留。
            </UI.Text>
            <Button asChild variant="ghost" className="self-start">
              <Link href="/topics">管理监控主题</Link>
            </Button>
          </UI.Content>
        ) : null}
      </UI.Content>
    </UI.Content>
  );
}
