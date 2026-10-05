"use client";
import * as UI from "@/components/ui/content";

import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
} from "@/components/ui/navigation-menu";

import { Spinner } from "@/components/ui/spinner";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
} from "@/components/ui/item";
import { Input } from "@/components/ui/input";
import { FieldLabel, Field } from "@/components/ui/field";

import Link from "next/link";
import { useId, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { getSitePublicationItem } from "@/api/gongkaifabu";
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";

import {
  LOCAL_CHANGE,
  SAVED_KEY,
  READ_KEY,
  IMPORT_MAX_CHARS,
  savedIds,
  readIds,
  toggleSaved,
  removeSaved,
  markRead,
  exportLocalBundle,
  importLocalBundle,
  clearLocalReading,
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

export function SaveItem({ id }: { id: string }) {
  const [saved, setSaved] = useState(false);
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
        variant="outline"
        onClick={() => {
          void toggleSaved(id)
            .then((value) => {
              setSaved(value);
            })
            .catch(() => toast.error("本机存储不可用，未保存收藏。"));
        }}
      >
        {saved ? "取消本机收藏" : "本机收藏"}
      </Button>
    </>
  );
}

export function SavedItems({ full = false }: { full?: boolean }) {
  const fieldId = useId();

  const [items, setItems] = useState<HotKeyAPI.PublicItemDetailView[]>([]);
  const [ids, setIds] = useState<string[]>([]);
  const [read, setRead] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(true);
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  const storageFailed = useRef(false);
  const [generation, setGeneration] = useState(0);
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
    let selected: string[] = [];
    let readingError = false;
    try {
      selected = savedIds(localStorage);
      readingError = Boolean(localReadingIssue(localStorage));
    } catch {
      readingError = true;
    }
    const frame = requestAnimationFrame(() => {
      setBusy(true);
      setIds(selected);
      setStorageUnavailable(readingError);
      if (readingError && !storageFailed.current)
        toast.error(
          "本机收藏无法读取。原始数据保留，请先导出原始数据后核查；不会覆盖它。",
        );
      storageFailed.current = readingError;
      const lastPage = Math.max(1, Math.ceil(selected.length / 20));
      if (page > lastPage) {
        setPage(lastPage);
        return;
      }
      try {
        setRead(readIds(localStorage));
      } catch {
        setRead([]);
      }
      void Promise.allSettled(
        selected
          .slice((page - 1) * 20, page * 20)
          .map((content_id) => getSitePublicationItem({ content_id })),
      ).then((results) => {
        if (active) {
          setItems(
            results.flatMap((result) =>
              result.status === "fulfilled" ? [result.value] : [],
            ),
          );
          setBusy(false);
          if (results.some((result) => result.status === "rejected"))
            toast.error("部分收藏暂时无法读取，请重新读取或检查当前许可。");
        }
      });
    });
    return () => {
      active = false;
      cancelAnimationFrame(frame);
    };
  }, [page, generation]);
  function download(raw: string, name: string) {
    const link = document.createElement("a");
    const url = URL.createObjectURL(
      new Blob([raw], { type: "application/json" }),
    );
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <UI.Content as="section">
      <UI.Heading level={2} className="font-medium">
        本机收藏{ids.length ? ` · ${ids.length}` : ""}
      </UI.Heading>
      <UI.Text className="text-muted-foreground mt-2 text-xs">
        最多 500 篇收藏与 5000 个已读标记，仅保留编号，阅读时重新检查许可。
      </UI.Text>
      {busy ? (
        <Item role="status" className="mt-4">
          <Spinner aria-hidden="true" />
          <ItemContent>
            <ItemDescription className="line-clamp-none">
              正在读取当前公开材料…
            </ItemDescription>
          </ItemContent>
        </Item>
      ) : storageUnavailable ? (
        <Alert className="mt-4">
          <AlertTitle>本机收藏暂不可读</AlertTitle>
          <AlertDescription>
            可以导出原始数据核查，或重新读取。
          </AlertDescription>
        </Alert>
      ) : items.length ? (
        <ItemGroup className="mt-4 flex flex-col gap-y-4">
          {items.map((item) => (
            <Item
              role="listitem"
              variant="default"
              key={item.id}
              className="flex items-start justify-between gap-3"
            >
              <ItemContent className="min-w-0 gap-3">
                <Link href={item.reading_url} className="text-sm leading-6">
                  {item.title}
                  {read.includes(item.id) ? (
                    <UI.Text
                      as="span"
                      className="text-muted-foreground ml-2 text-xs"
                    >
                      已读
                    </UI.Text>
                  ) : null}
                </Link>
                {full ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      void removeSaved(item.id).catch(() =>
                        toast.error("存储不可用，未删除。"),
                      )
                    }
                  >
                    移除
                  </Button>
                ) : null}
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
      ) : (
        <UI.Text className="text-muted-foreground mt-4 text-sm">
          {ids.length
            ? "本页收藏暂时不可公开读取，可稍后重试或移除。"
            : "还没有收藏。"}
        </UI.Text>
      )}
      {!busy && ids.slice((page - 1) * 20, page * 20).length > items.length ? (
        <UI.Text className="text-muted-foreground mt-3 text-xs">
          本页 {ids.slice((page - 1) * 20, page * 20).length - items.length}{" "}
          篇材料已撤回、许可变化或暂时无法读取。
        </UI.Text>
      ) : null}
      {full ? (
        <>
          {!busy ? (
            <ItemGroup className="mt-4 flex flex-col gap-y-3">
              {ids
                .slice((page - 1) * 20, page * 20)
                .filter((id) => !items.some((item) => item.id === id))
                .map((id) => (
                  <Item
                    role="listitem"
                    variant="default"
                    key={id}
                    className="flex items-start justify-between gap-3"
                  >
                    <ItemContent className="min-w-0 gap-3">
                      <UI.Text
                        as="span"
                        className="text-muted-foreground break-all"
                      >
                        暂时不可读取 · {id}
                      </UI.Text>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          void removeSaved(id).catch(() =>
                            toast.error("存储不可用，未删除。"),
                          )
                        }
                      >
                        移除
                      </Button>
                    </ItemContent>
                  </Item>
                ))}
            </ItemGroup>
          ) : null}
          <NavigationMenu
            viewport={false}
            className="my-5 max-w-full justify-start"
            aria-label="收藏分页"
          >
            <NavigationMenuList className="flex-wrap justify-start gap-2">
              {page > 1 ? (
                <NavigationMenuItem>
                  <Button variant="outline" onClick={() => setPage(page - 1)}>
                    上一页
                  </Button>
                </NavigationMenuItem>
              ) : null}
              <NavigationMenuItem>
                <UI.Text as="span" className="text-sm">
                  第 {page} / {Math.max(1, Math.ceil(ids.length / 20))} 页
                </UI.Text>
              </NavigationMenuItem>
              {page * 20 < ids.length ? (
                <NavigationMenuItem>
                  <Button variant="outline" onClick={() => setPage(page + 1)}>
                    下一页
                  </Button>
                </NavigationMenuItem>
              ) : null}
              <NavigationMenuItem>
                <Button
                  variant="outline"
                  onClick={() => setGeneration((old) => old + 1)}
                >
                  重新读取
                </Button>
              </NavigationMenuItem>
            </NavigationMenuList>
          </NavigationMenu>
          <UI.Content className="flex flex-wrap gap-3">
            <Button
              variant="outline"
              onClick={() => {
                try {
                  download(
                    JSON.stringify(exportLocalBundle(localStorage), null, 2),
                    "hotkey-reading-v1.json",
                  );
                } catch (error) {
                  toast.error(
                    error instanceof Error ? error.message : "无法导出。",
                  );
                }
              }}
            >
              导出收藏与已读
            </Button>
            <Field className="min-w-0 sm:max-w-sm">
              <FieldLabel htmlFor={`${fieldId}-local-reading-field-2`}>
                合并导入
              </FieldLabel>
              <Input
                aria-label="导入收藏备份"
                type="file"
                accept="application/json,.json"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file) return;
                  if (file.size > IMPORT_MAX_CHARS) {
                    toast.error("文件过大，上限 2 MB。");
                    return;
                  }
                  try {
                    const report = await importLocalBundle(await file.text());
                    const summary = `新增 ${report.savedAdded} 篇收藏、${report.readAdded} 个已读标记，跳过 ${report.skipped} 条。`;
                    if (report.readFailed)
                      toast.error(`${summary}已读标记写入失败；收藏已保存。`);
                    else toast.success(summary);
                  } catch (error) {
                    toast.error(
                      error instanceof Error ? error.message : "导入失败。",
                    );
                  }
                }}
                id={`${fieldId}-local-reading-field-2`}
              />
            </Field>
            <Button
              variant="outline"
              onClick={() => {
                try {
                  download(
                    JSON.stringify({
                      starredRaw: localStorage.getItem(SAVED_KEY),
                      readRaw: localStorage.getItem(READ_KEY),
                    }),
                    "hotkey-reading-raw.json",
                  );
                } catch {
                  toast.error("无法读取本机原始数据。");
                }
              }}
            >
              导出原始数据
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                void clearLocalReading()
                  .then(() => {
                    setPage(1);
                    toast.success("已清空本机收藏与已读标记。");
                  })
                  .catch(() => toast.error("存储不可用，未清空。"))
              }
            >
              明确清空本机数据
            </Button>
          </UI.Content>
        </>
      ) : (
        <Link
          href="/discover/starred"
          className="mt-4 inline-block text-xs underline"
        >
          管理全部收藏与导入导出
        </Link>
      )}
    </UI.Content>
  );
}
