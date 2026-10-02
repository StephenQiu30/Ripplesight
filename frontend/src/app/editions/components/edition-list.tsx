"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { listReportEditions, requestReportEdition } from "@/api/rizhouyuekan";
import { WorkspaceHeader } from "@/components/navigation/workspace-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EditionCard, editionError, editionKinds } from "./edition-parts";

export function EditionList() {
  const [kind, setKind] =
    useState<HotKeyAPI.EditionRequestInput["kind"]>("daily");
  const [rows, setRows] = useState<HotKeyAPI.EditionSummaryView[]>([]);
  const [before, setBefore] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [refresh, setRefresh] = useState(0);
  const [saving, setSaving] = useState(false);
  const [accepted, setAccepted] = useState<HotKeyAPI.EditionDetailView>();
  const operation = useRef<{ signature: string; id: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void listReportEditions(
      { kind, before_key: before, limit: 20 },
      { signal: controller.signal },
    )
      .then((items) => {
        if (!controller.signal.aborted) {
          setRows(items);
          setError(undefined);
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setRows([]);
          setError(editionError(err));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [kind, before, refresh]);

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const key = String(form.get("key") ?? "").trim();
    const reason = String(form.get("reason") ?? "").trim();
    const revision =
      rows.find((row) => row.kind === kind && row.key === key)?.revision ?? 0;
    const signature = JSON.stringify([kind, key, reason, revision]);
    if (operation.current?.signature !== signature) {
      operation.current = { signature, id: crypto.randomUUID() };
    }
    setSaving(true);
    setError(undefined);
    setAccepted(undefined);
    try {
      const row = await requestReportEdition({
        kind,
        key,
        reason,
        expected_revision: revision,
        operation_id: operation.current.id,
      });
      setAccepted(row);
      operation.current = null;
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(editionError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <WorkspaceHeader current="editions" />
      <main className="mx-auto max-w-6xl px-5 py-12 sm:px-8">
        <h1 className="text-3xl font-medium tracking-tight">日周月刊</h1>
        <p className="text-muted-foreground mt-4 leading-7">
          按北京时间的完整自然刊期编选资讯，阅读来源、关键事实和历史修订。
        </p>
        <nav aria-label="刊期类型" className="my-7 flex gap-3">
          {Object.entries(editionKinds).map(([key, label]) => (
            <Button
              key={key}
              variant={kind === key ? "secondary" : "outline"}
              aria-pressed={kind === key}
              onClick={() => {
                setKind(key as typeof kind);
                setBefore(undefined);
                setRows([]);
                setLoading(true);
                setAccepted(undefined);
              }}
            >
              {label}
            </Button>
          ))}
          <Button
            variant="ghost"
            onClick={() => {
              setLoading(true);
              setRefresh((n) => n + 1);
            }}
          >
            刷新
          </Button>
        </nav>
        {error ? (
          <Alert variant="destructive">
            <AlertTitle>刊期暂不可用</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <div className="grid gap-12 lg:grid-cols-3">
          <section className="lg:col-span-2" aria-label="刊期档案">
            {loading ? (
              <Skeleton className="h-32 w-full" />
            ) : rows.length ? (
              <ul>
                {rows.map((row) => (
                  <EditionCard key={row.id} row={row} />
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground py-10">
                暂无{editionKinds[kind]}刊期。
              </p>
            )}
            {rows.length === 20 ? (
              <Button
                variant="outline"
                className="mt-6"
                onClick={() => {
                  setBefore(rows.at(-1)?.key);
                  setLoading(true);
                }}
              >
                更早刊期
              </Button>
            ) : null}
            {before ? (
              <Button
                variant="ghost"
                className="mt-6"
                onClick={() => {
                  setBefore(undefined);
                  setLoading(true);
                }}
              >
                返回最新
              </Button>
            ) : null}
          </section>
          <aside>
            <h2 className="font-medium">编选{editionKinds[kind]}</h2>
            <form onSubmit={generate} className="mt-5 space-y-5">
              <label className="block space-y-2 text-sm">
                刊期
                <Input
                  name="key"
                  required
                  minLength={7}
                  maxLength={10}
                  placeholder={
                    kind === "daily"
                      ? "2026-10-01"
                      : kind === "weekly"
                        ? "2026-W39"
                        : "2026-09"
                  }
                />
              </label>
              <label className="block space-y-2 text-sm">
                编选原因
                <Input name="reason" required maxLength={1000} />
              </label>
              <p className="text-muted-foreground text-xs leading-6">
                请选择已结束的刊期。有新材料或需要重新编选时会保留此前修订。
              </p>
              <Button type="submit" disabled={saving}>
                {saving ? "正在受理…" : "提交编选"}
              </Button>
            </form>
            {accepted ? (
              <p role="status" className="mt-5 text-sm">
                已受理。
                <Link href={`/editions/${accepted.id}`} className="underline">
                  查看进度与正文
                </Link>
              </p>
            ) : null}
          </aside>
        </div>
      </main>
    </>
  );
}
