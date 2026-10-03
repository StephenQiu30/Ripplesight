"use client";
import { Separator } from "@/components/ui/separator";

import {
  Item,
  ItemContent,
  ItemGroup,
  ItemDescription,
} from "@/components/ui/item";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FieldGroup,
  FieldLabel,
  Field,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useEffect, useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "@/request";
import {
  correctReportEdition,
  getReportEdition,
  listReportEditionRevisions,
} from "@/api/rizhouyuekan";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  EditionCard,
  editionError,
  editionKinds,
  editionStates,
} from "./edition-parts";

function EditionReferences({
  ids,
  entries,
}: {
  ids: string[];
  entries: HotKeyAPI.ReportPublicationCandidate[];
}) {
  return (
    <ItemGroup className="flex flex-col gap-y-5">
      {ids.map((id) => {
        const entry = entries.find((row) => row.content_id === id);
        return entry ? (
          <Item
            role="listitem"
            variant="default"
            key={id}
            className="flex flex-col gap-y-2"
          >
            <ItemContent className="min-w-0 gap-3">
              <Link href={`/items/${id}`} className="leading-7 font-medium">
                {entry.title_zh}
              </Link>
              <ItemDescription className="line-clamp-none leading-7">
                {entry.summary_zh}
              </ItemDescription>
              <ItemDescription className="line-clamp-none">
                {entry.source_name}
                {entry.first_party ? " · 一手来源" : ""}
              </ItemDescription>
            </ItemContent>
          </Item>
        ) : null;
      })}
    </ItemGroup>
  );
}

function EditionCorrection({
  row,
  saved,
}: {
  row: HotKeyAPI.EditionDetailView;
  saved: (row: HotKeyAPI.EditionDetailView) => void;
}) {
  const fieldId = useId();

  const [busy, setBusy] = useState(false);
  const operation = useRef<{ signature: string; id: string } | null>(null);
  const content = row.content;
  if (!content || row.historical_revision || !row.valid) return null;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const changes = {
      expected_revision: row.revision,
      title: String(form.get("title") ?? "").trim(),
      lead: String(form.get("lead") ?? "").trim(),
      reason: String(form.get("reason") ?? "").trim(),
      highlights: form.getAll("highlights").map(String),
      themes: (content?.themes ?? []).map((theme, index) => ({
        heading: String(form.get(`heading-${index}`) ?? "").trim(),
        summary: String(form.get(`summary-${index}`) ?? "").trim(),
        content_ids: theme.content_ids,
      })),
    };
    const signature = JSON.stringify(changes);
    if (operation.current?.signature !== signature)
      operation.current = { signature, id: crypto.randomUUID() };
    setBusy(true);
    try {
      const next = await correctReportEdition(
        { edition_id: row.id },
        { ...changes, operation_id: operation.current.id },
      );
      operation.current = null;
      toast.success("刊期新修订已保存。");
      saved(next);
    } catch (err) {
      if (err instanceof ApiRequestError && err.kind === "cancelled") return;
      toast.error(editionError(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Collapsible className="mt-12 pt-6">
      <Separator className="mb-6" />
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
        >
          <span className="min-w-0 text-left">修订本刊</span>
          <ChevronDownIcon
            aria-hidden="true"
            data-icon="inline-end"
            className="group-data-[state=open]:rotate-180"
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent forceMount className="data-[state=closed]:hidden">
        <form onSubmit={submit}>
          <FieldGroup className="mt-6 flex max-w-3xl flex-col gap-y-5">
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-edition-detail-field-1`}>
                标题
              </FieldLabel>
              <Input
                name="title"
                required
                maxLength={120}
                defaultValue={content.title}
                id={`${fieldId}-edition-detail-field-1`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-edition-detail-field-2`}>
                导读
              </FieldLabel>
              <Textarea
                name="lead"
                required
                maxLength={1500}
                defaultValue={content.lead}
                rows={5}
                id={`${fieldId}-edition-detail-field-2`}
              />
            </Field>
            <FieldSet className="flex flex-col gap-y-3">
              <FieldLegend className="mb-3 text-sm">
                重点资讯（最多六项）
              </FieldLegend>
              {content.entries.map((entry) => (
                <Field
                  key={entry.content_id}
                  orientation="horizontal"
                  className="w-auto"
                >
                  <Checkbox
                    name="highlights"
                    value={entry.content_id}
                    defaultChecked={content.highlights.includes(
                      entry.content_id,
                    )}
                    id={`${fieldId}-edition-detail-field-3-${entry.content_id}`}
                  />
                  <FieldLabel
                    htmlFor={`${fieldId}-edition-detail-field-3-${entry.content_id}`}
                  >
                    {entry.title_zh}
                  </FieldLabel>
                </Field>
              ))}
            </FieldSet>
            {content.themes.map((theme, i) => (
              <FieldSet key={i} className="flex flex-col gap-y-3">
                <FieldLegend className="text-sm">主题 {i + 1}</FieldLegend>
                <Input
                  aria-label={`主题 ${i + 1} 标题`}
                  name={`heading-${i}`}
                  required
                  maxLength={60}
                  defaultValue={theme.heading}
                />
                <Textarea
                  aria-label={`主题 ${i + 1} 摘要`}
                  name={`summary-${i}`}
                  required
                  maxLength={800}
                  defaultValue={theme.summary}
                />
              </FieldSet>
            ))}
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-edition-detail-field-4`}>
                修订原因
              </FieldLabel>
              <Input
                name="reason"
                required
                maxLength={1000}
                id={`${fieldId}-edition-detail-field-4`}
              />
            </Field>
            <Button type="submit" disabled={busy}>
              {busy ? "保存中…" : "保存新修订"}
            </Button>
          </FieldGroup>
        </form>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function EditionDetail({ editionId }: { editionId: string }) {
  const router = useRouter();
  const [row, setRow] = useState<HotKeyAPI.EditionDetailView>();
  const [history, setHistory] = useState<HotKeyAPI.EditionSummaryView[]>([]);
  const [loadFailed, setLoadFailed] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function read() {
      try {
        const next = await getReportEdition(
          { edition_id: editionId },
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setRow(next);
        setLoadFailed(false);
        if (next.status === "queued" || next.status === "running")
          timer = setTimeout(read, 5000);
      } catch (err) {
        if (
          !controller.signal.aborted &&
          !(err instanceof ApiRequestError && err.kind === "cancelled")
        ) {
          setRow(undefined);
          setLoadFailed(true);
          toast.error(editionError(err));
        }
      }
    }
    void read();
    void listReportEditionRevisions(
      { edition_id: editionId },
      { signal: controller.signal },
    )
      .then((rows) => {
        if (!controller.signal.aborted) {
          setHistory(rows);
          setHistoryError(false);
        }
      })
      .catch((err: unknown) => {
        if (
          !controller.signal.aborted &&
          !(err instanceof ApiRequestError && err.kind === "cancelled")
        ) {
          setHistory([]);
          setHistoryError(true);
          toast.error("历史修订读取失败，刷新后可以重试。");
        }
      });
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [editionId, refresh]);
  const content = row?.valid && row.status === "complete" ? row.content : null;
  return (
    <>
      <div>
        <div className="mb-8 flex justify-between gap-3">
          <Link href="/editions" className="text-muted-foreground text-sm">
            返回刊期档案
          </Link>
          <Button variant="outline" onClick={() => setRefresh((n) => n + 1)}>
            刷新刊期
          </Button>
        </div>
        {loadFailed ? (
          <Alert variant="destructive">
            <AlertTitle>正文暂不可读</AlertTitle>
            <AlertDescription>
              刷新后可以重新检查当前刊期许可。
            </AlertDescription>
          </Alert>
        ) : null}
        {!row && !loadFailed ? <Skeleton className="h-40 w-full" /> : null}
        {row ? (
          <>
            <p className="text-muted-foreground text-sm">
              {editionKinds[row.kind]} · {row.key} · 修订 {row.revision}
              {row.historical_revision ? " · 历史修订" : ""}
            </p>
            <h1 className="mt-5 text-3xl leading-tight font-medium tracking-tight">
              {content?.title ?? `${row.key} ${editionKinds[row.kind]}`}
            </h1>
            {!content ? (
              <Alert className="mt-8">
                <AlertTitle>{editionStates[row.status]}</AlertTitle>
                <AlertDescription>
                  {row.status === "stale"
                    ? "材料或阅读许可已变更，本刊正文暂不可读。"
                    : row.status === "unknown"
                      ? "生成响应需要核实，请在任务记录中查看处理状态。"
                      : "正文将在编选完成并通过材料检查后显示。"}
                  {row.job_id ? (
                    <Link
                      href={`/jobs/${row.job_id}`}
                      className="mt-3 block underline"
                    >
                      查看任务记录
                    </Link>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : (
              <>
                <p className="text-muted-foreground mt-7 text-lg leading-8 whitespace-pre-wrap">
                  {content.lead}
                </p>
                <Separator className="mt-8" />
                <dl className="my-6 grid grid-cols-2 gap-5 sm:grid-cols-4">
                  {[
                    ["资讯", content.metrics.selected_count],
                    ["事实", content.metrics.facts_count],
                    ["来源", content.metrics.sources_count],
                    ["一手材料", content.metrics.first_party_count],
                  ].map(([label, count]) => (
                    <div key={label}>
                      <dt className="text-muted-foreground text-xs">{label}</dt>
                      <dd className="mt-2 text-2xl">{count}</dd>
                    </div>
                  ))}
                </dl>
                <Separator className="mb-8" />
                {content.highlights.length ? (
                  <section className="my-10 flex flex-col gap-y-6">
                    <h2 className="text-xl font-medium">重点关注</h2>
                    <EditionReferences
                      ids={content.highlights}
                      entries={content.entries}
                    />
                  </section>
                ) : null}
                {content.themes.map((theme) => (
                  <section
                    key={theme.heading}
                    className="my-10 flex flex-col gap-y-5"
                  >
                    <h2 className="text-xl font-medium">{theme.heading}</h2>
                    <p className="text-muted-foreground leading-7 whitespace-pre-wrap">
                      {theme.summary}
                    </p>
                    <EditionReferences
                      ids={theme.content_ids}
                      entries={content.entries}
                    />
                  </section>
                ))}
                {content.sections
                  .filter((section) => section.content_ids.length)
                  .map((section) => (
                    <section
                      key={section.label}
                      className="my-10 flex flex-col gap-y-6"
                    >
                      <h2 className="text-xl font-medium">{section.label}</h2>
                      <EditionReferences
                        ids={section.content_ids}
                        entries={content.entries}
                      />
                    </section>
                  ))}
                {content.flashes.length ? (
                  <section className="my-10 flex flex-col gap-y-6">
                    <h2 className="text-xl font-medium">快讯</h2>
                    <EditionReferences
                      ids={content.flashes}
                      entries={content.entries}
                    />
                  </section>
                ) : null}
                <div className="flex flex-wrap gap-3">
                  <Button asChild variant="outline">
                    <a href={`/reports/${row.kind}/${row.key}.md`}>
                      当前刊期 Markdown
                    </a>
                  </Button>
                  <Button asChild variant="outline">
                    <a href={`/reports/${row.kind}/${row.key}/poster.svg`}>
                      刊期分享海报
                    </a>
                  </Button>
                </div>
                <EditionCorrection
                  key={row.id}
                  row={row}
                  saved={(next) => {
                    router.push(`/editions/${next.id}`);
                  }}
                />
              </>
            )}
          </>
        ) : null}
        <section className="mt-12 pt-6">
          <Separator className="mb-6" />
          <h2 className="font-medium">历史修订</h2>
          {historyError ? (
            <Alert className="mt-4">
              <AlertTitle>历史修订暂不可读</AlertTitle>
              <AlertDescription>刷新后可以重新读取历史修订。</AlertDescription>
            </Alert>
          ) : (
            <ItemGroup>
              {history.map((item) => (
                <EditionCard row={item} key={item.id} />
              ))}
            </ItemGroup>
          )}
        </section>
      </div>
    </>
  );
}
