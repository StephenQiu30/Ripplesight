"use client";
import { Input } from "@/components/ui/input";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import { FieldLabel, Field } from "@/components/ui/field";

import Link from "next/link";
import { useId, useEffect, useState } from "react";

import { getSitePublicationItem } from "@/api/gongkaifabu";
import { Button } from "@/components/ui/button";

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
  themePreference,
  saveTheme,
  applyTheme,
  localReadingIssue,
} from "./local-state";
export { savedIds } from "./local-state";

export function LocalThemeInitializer() {
  useEffect(() => {
    const update = () => {
      try {
        applyTheme(themePreference(localStorage));
      } catch {
        applyTheme("auto");
      }
    };
    const frame = requestAnimationFrame(update);
    window.addEventListener("storage", update);
    window.addEventListener(LOCAL_CHANGE, update);
    const media = matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("storage", update);
      window.removeEventListener(LOCAL_CHANGE, update);
      media.removeEventListener("change", update);
    };
  }, []);
  return null;
}

export function LocalReadingPreferences() {
  const fieldId = useId();

  const [theme, setTheme] = useState<"light" | "dark" | "auto">("auto");
  useEffect(() => {
    const update = () => {
      try {
        const value = themePreference(localStorage);
        applyTheme(value);
        setTheme(value);
      } catch {
        /* Optional state. */
      }
    };
    const frame = requestAnimationFrame(update);
    window.addEventListener("storage", update);
    window.addEventListener(LOCAL_CHANGE, update);
    const media = matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("storage", update);
      window.removeEventListener(LOCAL_CHANGE, update);
      media.removeEventListener("change", update);
    };
  }, []);
  return (
    <Field orientation="horizontal" className="w-auto">
      <FieldLabel htmlFor={`${fieldId}-local-reading-field-1`}>
        阅读主题{" "}
      </FieldLabel>
      <Select
        value={theme}
        onValueChange={(selectedValue) => {
          const value = selectedValue as "light" | "dark" | "auto";
          try {
            saveTheme(value);
            setTheme(value);
          } catch {
            applyTheme(value);
            setTheme(value);
          }
        }}
      >
        <SelectTrigger
          aria-label="阅读主题"
          id={`${fieldId}-local-reading-field-1`}
          className="w-36 min-w-0"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper">
          <SelectGroup>
            <SelectLabel className="sr-only">阅读主题 </SelectLabel>
            <SelectItem value="auto" className="whitespace-normal">
              跟随系统
            </SelectItem>
            <SelectItem value="light" className="whitespace-normal">
              浅色
            </SelectItem>
            <SelectItem value="dark" className="whitespace-normal">
              深色
            </SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  );
}

export function MarkItemRead({ id }: { id: string }) {
  useEffect(() => {
    void markRead(id).catch(() => undefined);
  }, [id]);
  return null;
}

export function SaveItem({ id }: { id: string }) {
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    const update = () => {
      try {
        setSaved(savedIds(localStorage).includes(id));
      } catch {
        setError(true);
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
              setError(false);
            })
            .catch(() => setError(true));
        }}
      >
        {saved ? "取消本机收藏" : "本机收藏"}
      </Button>
      {error ? (
        <p role="status" className="text-muted-foreground text-xs">
          本机存储不可用，未保存。
        </p>
      ) : null}
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
  const [notice, setNotice] = useState("");
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
      if (readingError)
        setNotice(
          "本机收藏无法读取。原始数据保留，请先导出原始数据后核查；不会覆盖它。",
        );
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
    <section>
      <h2 className="font-medium">
        本机收藏{ids.length ? ` · ${ids.length}` : ""}
      </h2>
      <p className="text-muted-foreground mt-2 text-xs">
        最多 500 篇收藏与 5000 个已读标记，仅保留编号，阅读时重新检查许可。
      </p>
      {busy ? (
        <p role="status" className="mt-4 text-sm">
          正在读取当前公开材料…
        </p>
      ) : items.length ? (
        <ul className="mt-4 flex flex-col gap-y-4">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex items-start justify-between gap-3"
            >
              <Link href={item.reading_url} className="text-sm leading-6">
                {item.title}
                {read.includes(item.id) ? (
                  <span className="text-muted-foreground ml-2 text-xs">
                    已读
                  </span>
                ) : null}
              </Link>
              {full ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    void removeSaved(item.id).catch(() =>
                      setNotice("存储不可用，未删除。"),
                    )
                  }
                >
                  移除
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-4 text-sm">
          {ids.length
            ? "本页收藏暂时不可公开读取，可稍后重试或移除。"
            : "还没有收藏。"}
        </p>
      )}
      {!busy && ids.slice((page - 1) * 20, page * 20).length > items.length ? (
        <p className="text-muted-foreground mt-3 text-xs">
          本页 {ids.slice((page - 1) * 20, page * 20).length - items.length}{" "}
          篇材料已撤回、许可变化或暂时无法读取。
        </p>
      ) : null}
      {full ? (
        <>
          {!busy ? (
            <ul className="mt-4 flex flex-col gap-y-3">
              {ids
                .slice((page - 1) * 20, page * 20)
                .filter((id) => !items.some((item) => item.id === id))
                .map((id) => (
                  <li
                    key={id}
                    className="flex items-start justify-between gap-3 text-xs"
                  >
                    <span className="text-muted-foreground break-all">
                      暂时不可读取 · {id}
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        void removeSaved(id).catch(() =>
                          setNotice("存储不可用，未删除。"),
                        )
                      }
                    >
                      移除
                    </Button>
                  </li>
                ))}
            </ul>
          ) : null}
          <nav className="my-5 flex items-center gap-3" aria-label="收藏分页">
            {page > 1 ? (
              <Button variant="outline" onClick={() => setPage(page - 1)}>
                上一页
              </Button>
            ) : null}
            <span className="text-sm">
              第 {page} / {Math.max(1, Math.ceil(ids.length / 20))} 页
            </span>
            {page * 20 < ids.length ? (
              <Button variant="outline" onClick={() => setPage(page + 1)}>
                下一页
              </Button>
            ) : null}
            <Button
              variant="outline"
              onClick={() => setGeneration((old) => old + 1)}
            >
              重新读取
            </Button>
          </nav>
          <div className="flex flex-wrap gap-3">
            <Button
              variant="outline"
              onClick={() => {
                try {
                  download(
                    JSON.stringify(exportLocalBundle(localStorage), null, 2),
                    "hotkey-reading-v1.json",
                  );
                } catch (error) {
                  setNotice(
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
                    setNotice("文件过大，上限 2 MB。");
                    return;
                  }
                  try {
                    const report = await importLocalBundle(await file.text());
                    setNotice(
                      `新增 ${report.savedAdded} 篇收藏、${report.readAdded} 个已读标记，跳过 ${report.skipped} 条。${report.readFailed ? "已读标记写入失败；收藏已保存。" : ""}`,
                    );
                  } catch (error) {
                    setNotice(
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
                  setNotice("无法读取本机原始数据。");
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
                    setNotice("已清空本机收藏与已读标记。");
                  })
                  .catch(() => setNotice("存储不可用，未清空。"))
              }
            >
              明确清空本机数据
            </Button>
          </div>
          <p role="status" className="text-muted-foreground mt-3 text-sm">
            {notice}
          </p>
        </>
      ) : (
        <Link
          href="/discover/starred"
          className="mt-4 inline-block text-xs underline"
        >
          管理全部收藏与导入导出
        </Link>
      )}
    </section>
  );
}
