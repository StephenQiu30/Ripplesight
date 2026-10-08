"use client";
import * as UI from "@/components/ui/content";

import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { ItemGroup } from "@/components/ui/item";
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";

import Link from "next/link";
import { useId, useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "@/request";
import { listReportEditions, requestReportEdition } from "@/api/rizhouyuekan";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { EditionCard, editionError, editionKinds } from "./edition-parts";

export function EditionList() {
  const fieldId = useId();

  const [kind, setKind] =
    useState<HotKeyAPI.EditionRequestInput["kind"]>("daily");
  const [rows, setRows] = useState<HotKeyAPI.EditionSummaryView[]>([]);
  const [before, setBefore] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [saving, setSaving] = useState(false);
  const [accepted, setAccepted] = useState<HotKeyAPI.EditionDetailView>();
  const permissionVersion = useRef(0);
  const deniedRef = useRef(false);
  const operation = useRef<{ signature: string; id: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const readVersion = permissionVersion.current;
    void listReportEditions(
      { kind, before_key: before, limit: 20 },
      { signal: controller.signal },
    )
      .then((items) => {
        if (
          !controller.signal.aborted &&
          readVersion === permissionVersion.current
        ) {
          setRows(items);
          setLoadFailed(false);
          setForbidden(false);
          deniedRef.current = false;
        }
      })
      .catch((err: unknown) => {
        if (
          !controller.signal.aborted &&
          readVersion === permissionVersion.current &&
          !(err instanceof ApiRequestError && err.kind === "cancelled")
        ) {
          setRows([]);
          setLoadFailed(true);
          const denied =
            err instanceof ApiRequestError &&
            (err.status === 401 || err.status === 403);
          if (denied) setForbidden(true);
          if (denied) {
            permissionVersion.current += 1;
            deniedRef.current = true;
            setAccepted(undefined);
          }
          toast.error(editionError(err));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [kind, before, refresh]);

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving || deniedRef.current) return;
    const writeVersion = permissionVersion.current;
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
    setAccepted(undefined);
    try {
      const row = await requestReportEdition({
        kind,
        key,
        reason,
        expected_revision: revision,
        operation_id: operation.current.id,
      });
      if (writeVersion !== permissionVersion.current) return;
      setAccepted(row);
      toast.success("刊期编选已受理，可查看进度与正文。");
      operation.current = null;
      setRefresh((value) => value + 1);
    } catch (err) {
      if (writeVersion !== permissionVersion.current) return;
      if (err instanceof ApiRequestError && err.kind === "cancelled") return;
      toast.error(editionError(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <UI.Content>
        <UI.Heading level={1} className="text-3xl font-medium tracking-tight">
          日周月刊
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-4 leading-7">
          按北京时间的完整自然刊期编选资讯，阅读来源、关键事实和历史修订。
        </UI.Text>
        <UI.Content className="my-7 flex flex-wrap gap-3">
          <ToggleGroup
            type="single"
            variant="outline"
            value={kind}
            aria-label="刊期类型"
            onValueChange={(value) => {
              if (value) {
                setKind(value as typeof kind);
                setBefore(undefined);
                setRows([]);
                setLoading(true);
                setAccepted(undefined);
              }
            }}
          >
            {Object.entries(editionKinds).map(([key, label]) => (
              <ToggleGroupItem key={key} value={key}>
                {label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <Button
            variant="ghost"
            onClick={() => {
              setLoading(true);
              setRefresh((n) => n + 1);
            }}
          >
            刷新
          </Button>
        </UI.Content>
        {loadFailed ? (
          <Alert variant="destructive">
            <AlertTitle>
              {forbidden ? "无权读取刊期" : "刊期暂不可用"}
            </AlertTitle>
            <AlertDescription>刷新后可以重新读取刊期档案。</AlertDescription>
          </Alert>
        ) : null}
        <UI.Content className="grid gap-12 lg:grid-cols-3">
          <UI.Content
            as="section"
            className="lg:col-span-2"
            aria-label="刊期档案"
          >
            {loading ? (
              <UI.Content
                role="status"
                aria-busy="true"
                aria-label="正在读取刊期档案"
              >
                <Skeleton className="h-32 w-full" />
              </UI.Content>
            ) : loadFailed ? null : rows.length ? (
              <ItemGroup>
                {rows.map((row) => (
                  <EditionCard key={row.id} row={row} />
                ))}
              </ItemGroup>
            ) : (
              <Empty className="py-10">
                <EmptyHeader>
                  <EmptyDescription>
                    暂无{editionKinds[kind]}刊期。
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
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
          </UI.Content>
          <UI.Content as="aside">
            <UI.Heading level={2} className="font-medium">
              编选{editionKinds[kind]}
            </UI.Heading>
            <UI.Form onSubmit={generate}>
              <FieldGroup className="mt-5 flex flex-col gap-y-5">
                <Field className="min-w-0">
                  <FieldLabel htmlFor={`${fieldId}-edition-list-field-1`}>
                    刊期
                  </FieldLabel>
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
                    id={`${fieldId}-edition-list-field-1`}
                  />
                </Field>
                <Field className="min-w-0">
                  <FieldLabel htmlFor={`${fieldId}-edition-list-field-2`}>
                    编选原因
                  </FieldLabel>
                  <Input
                    name="reason"
                    required
                    maxLength={1000}
                    id={`${fieldId}-edition-list-field-2`}
                  />
                </Field>
                <UI.Text className="text-muted-foreground text-xs leading-6">
                  请选择已结束的刊期。有新材料或需要重新编选时会保留此前修订。
                </UI.Text>
                <Button type="submit" disabled={saving || forbidden}>
                  {saving ? "正在受理…" : "提交编选"}
                </Button>
              </FieldGroup>
            </UI.Form>
            {accepted ? (
              <Alert role="status" className="mt-5">
                <AlertDescription>
                  已受理。
                  <Link href={`/editions/${accepted.id}`} className="underline">
                    查看进度与正文
                  </Link>
                </AlertDescription>
              </Alert>
            ) : null}
          </UI.Content>
        </UI.Content>
      </UI.Content>
    </>
  );
}
