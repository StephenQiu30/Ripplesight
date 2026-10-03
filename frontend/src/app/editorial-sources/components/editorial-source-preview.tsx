"use client";
import { Separator } from "@/components/ui/separator";

import {
  Item,
  ItemContent,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  getEditorialSourcePreview,
  previewEditorialSourceSample,
  previewStoredEditorialSource,
  reviewEditorialSourcePreview,
} from "@/api/bianjilaiyuan";
import { safeExternalHref } from "@/app/content/components/content-presenters";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

type Props = {
  token: string;
  configurationJson: string;
  kind: HotKeyAPI.EditorialSourceKind;
  profileId: string | null;
  expectedRevision: number;
  sourceEnabled: boolean;
};
const localKinds = new Set<HotKeyAPI.EditorialSourceKind>([
  "rss",
  "web_list",
  "json_list",
]);
const statuses: Record<HotKeyAPI.EditorialSourcePreviewView["status"], string> =
  {
    complete: "本次试抓完成",
    partial: "本次试抓部分完成",
    blocked: "本次试抓未获准",
    unknown: "结果未知",
  };

export function EditorialSourcePreview({
  token,
  configurationJson,
  kind,
  profileId,
  expectedRevision,
  sourceEnabled,
}: Props) {
  const [sample, setSample] = useState("");
  const [reason, setReason] = useState("");
  const [preview, setPreview] =
    useState<HotKeyAPI.EditorialSourcePreviewView | null>(null);
  const [job, setJob] = useState<HotKeyAPI.JobView | null>(null);
  const [jobStatus, setJobStatus] = useState<HotKeyAPI.JobStatusView | null>(
    null,
  );
  const [busy, setBusy] = useState(false);

  const [reviewed, setReviewed] = useState(false);
  const [remoteAttempt, setRemoteAttempt] = useState(0);
  const epoch = useRef(0);
  const operations = useRef(new Map<string, string>());
  const headers = { "X-HotKey-Operator-Token": token, "X-HotKey-CSRF": "1" };
  useEffect(
    () => () => {
      epoch.current += 1;
    },
    [],
  );
  function operation(value: object) {
    const key = JSON.stringify(value);
    if (!operations.current.has(key))
      operations.current.set(key, crypto.randomUUID());
    return operations.current.get(key)!;
  }
  async function perform(
    work: (current: () => boolean) => Promise<void>,
    operationId?: string,
  ) {
    const captured = epoch.current;
    const current = () => epoch.current === captured;
    setBusy(true);

    try {
      await work(current);
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.kind === "cancelled")
        return;
      if (!current()) return;
      const unconfirmed =
        cause instanceof ApiRequestError &&
        ["network", "timeout", "protocol"].includes(cause.kind);
      toast.error(
        `${cause instanceof ApiRequestError ? cause.message : "试抓读取或解析失败，请检查配置。"}${unconfirmed && operationId ? ` 操作响应尚未确认；操作编号 ${operationId}。重试同一输入会复用此编号，请先核对任务。` : ""}`,
      );
    } finally {
      if (current()) setBusy(false);
    }
  }
  function parseSample() {
    if (new TextEncoder().encode(sample).byteLength > 1_000_000) {
      toast.error(
        "样本不能超过 1 MB（1,000,000 UTF-8 字节），请缩小样本再解析。",
      );
      return;
    }
    let configuration: HotKeyAPI.EditorialSourceConfiguration;
    try {
      const parsed: unknown = JSON.parse(configurationJson);
      if (
        !parsed ||
        typeof parsed !== "object" ||
        !("kind" in parsed) ||
        parsed.kind !== kind
      )
        throw new Error();
      configuration = parsed as HotKeyAPI.EditorialSourceConfiguration;
    } catch {
      toast.error("配置 JSON 必须是当前来源类型的对象。");
      return;
    }
    const input = { configuration, sample, reason: reason.trim() };
    const id = operation({ action: "sample", ...input });
    void perform(async (current) => {
      const result = await previewEditorialSourceSample(
        { ...input, operation_id: id },
        { headers },
      );
      if (current()) {
        setPreview(result);
        setJob(null);
        setJobStatus(null);
        setReviewed(false);
      }
    }, id);
  }
  function remote() {
    if (!profileId) return;
    const input = {
      expected_revision: expectedRevision,
      reason: reason.trim(),
    };
    const id = operation({
      action: "remote",
      profileId,
      remoteAttempt,
      ...input,
    });
    void perform(async (current) => {
      const accepted = await previewStoredEditorialSource(
        { profile_id: profileId },
        { ...input, operation_id: id },
        { headers },
      );
      if (current()) {
        setJob(accepted);
        setJobStatus(null);
        setPreview(null);
        setReviewed(false);
      }
    }, id);
  }
  function read() {
    if (!job) return;
    void perform(async (current) => {
      const result = await getEditorialSourcePreview(
        { job_id: job.id },
        { headers },
      );
      if (current()) {
        setJobStatus(result.job);
        setPreview(result.preview ?? null);
      }
    });
  }
  function reviewUnknown() {
    if (!job || preview?.status !== "unknown" || reviewed) return;
    const input = {
      preview_operation_id: job.operation_id,
      expected_revision: expectedRevision,
      reason: reason.trim(),
    };
    const id = operation({ action: "review", jobId: job.id, ...input });
    void perform(async (current) => {
      await reviewEditorialSourcePreview(
        { job_id: job.id },
        { ...input, operation_id: id },
        { headers },
      );
      if (current()) {
        setReviewed(true);
        setRemoteAttempt((attempt) => attempt + 1);
      }
    }, id);
  }
  const unsupported = kind === "mp_account" || kind === "external";
  const allowed = !!token && !!reason.trim() && !busy;
  return (
    <Item variant="muted" asChild>
      <section aria-label="配置试抓" className="flex flex-col gap-y-4 p-5">
        <ItemContent className="min-w-0 gap-3">
          <ItemTitle className="line-clamp-none w-full">
            <h3>配置试抓</h3>
          </ItemTitle>
          <ItemDescription className="line-clamp-none leading-7">
            试抓不写入正式材料、不推进采集游标。本地样本只解析当前表单；远程试抓使用已保存配置，可能产生来源费用，仍需现行许可与预算。
          </ItemDescription>
          {unsupported ? (
            <p>公众号与外部摄入不支持试抓；请使用对应的正式有界入口。</p>
          ) : (
            <>
              <Label htmlFor="source-preview-reason">试抓原因</Label>
              <Input
                id="source-preview-reason"
                value={reason}
                maxLength={1000}
                onChange={(event) => setReason(event.target.value)}
              />
              {localKinds.has(kind) ? (
                <>
                  <Label htmlFor="source-preview-sample">本地样本文本</Label>
                  <Textarea
                    id="source-preview-sample"
                    value={sample}
                    maxLength={1_000_000}
                    className="min-h-36 font-mono text-sm"
                    onChange={(event) => setSample(event.target.value)}
                  />
                  <ItemDescription className="line-clamp-none">
                    粘贴 RSS/XML、网页/Markdown 或 JSON 样本，最多 1
                    MB（1,000,000 UTF-8 字节），不存储样本文本，不请求来源网站。
                  </ItemDescription>
                  <Button
                    variant="outline"
                    disabled={!allowed || !sample.trim()}
                    onClick={parseSample}
                  >
                    解析本地样本
                  </Button>
                </>
              ) : (
                <ItemDescription className="line-clamp-none">
                  X 本地样本解析未提供；保存并批准官方连接后可受理单页远程试抓。
                </ItemDescription>
              )}
              <div className="flex flex-col gap-y-3 pt-4">
                <Separator />
                <p className="text-sm">
                  {profileId
                    ? `远程试抓预期来源修订 ${expectedRevision}。未保存的表单改动不会参与远程试抓。`
                    : "远程试抓需要先保存关闭来源配置，再批准许可与来源开关。"}
                </p>
                <p className="text-muted-foreground text-sm">
                  远程试抓只读列表，X 限单页；网页不抓取详情。仅显示最多 20
                  条摘要，不能用来证明全历史完整。
                </p>
                <Button
                  disabled={
                    !allowed ||
                    !profileId ||
                    !sourceEnabled ||
                    (!!job && !reviewed) ||
                    (preview?.status === "unknown" && !reviewed)
                  }
                  onClick={remote}
                >
                  受理远程试抓
                </Button>
                {profileId && !sourceEnabled ? (
                  <p className="text-muted-foreground text-sm">
                    已保存来源尚未启用；本地样本仍可解析。
                  </p>
                ) : null}
              </div>
            </>
          )}
          {job ? (
            <div className="flex flex-col gap-y-3 text-sm">
              <p>
                试抓任务 {jobStatus?.status ?? job.status} ·{" "}
                <Link
                  href={`/jobs/${job.id}`}
                  className="underline underline-offset-4"
                >
                  查看任务回执
                </Link>
              </p>
              <Button
                variant="outline"
                disabled={busy || !token}
                onClick={read}
              >
                读取试抓结果
              </Button>
              {!preview ? (
                <Empty>
                  <EmptyHeader>
                    <EmptyDescription>
                      尚无可读试抓结果，请按任务状态处理后再次读取。读取不会发起新的来源请求。
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              ) : null}
            </div>
          ) : null}
          {preview ? (
            <div className="flex flex-col gap-y-3 text-sm">
              <Alert role="status">
                <AlertDescription>
                  {statuses[preview.status]} ·{" "}
                  {preview.mode === "sample" ? "本地样本" : "远程列表"} ·
                  本次候选{preview.count} · 展示 {preview.items.length} ·{" "}
                  {preview.ms} ms · 请求数 {preview.requests}
                </AlertDescription>
              </Alert>
              {preview.reason ? (
                <p className="break-words">{preview.reason}</p>
              ) : null}
              {preview.status === "unknown" ? (
                <div className="flex flex-col gap-y-3">
                  <p>
                    请先在任务回执核验未知结果，不会自动重试或额外发送收费请求。人工核对保留原未知结果与保守预算回执。
                  </p>
                  {reviewed ? (
                    <p>
                      已记录人工核对；原结果仍为未知。如确需再次试抓，请显式点击受理远程试抓，新任务仍需当前许可与预算。
                    </p>
                  ) : job?.operation_id ? (
                    <Button
                      variant="outline"
                      disabled={!allowed}
                      onClick={reviewUnknown}
                    >
                      已核对未知试抓
                    </Button>
                  ) : null}
                </div>
              ) : null}
              {!preview.items.length && preview.status === "complete" ? (
                <p>本次已完成解析，未发现候选；不表示来源历史为空。</p>
              ) : null}
              {preview.items.map((item, index) => (
                <Item variant="muted" key={`${item.url}:${index}`} asChild>
                  <article className="flex flex-col gap-y-2 p-3">
                    <ItemContent className="min-w-0 gap-3">
                      <p className="font-medium">{item.title}</p>
                      <ItemDescription className="line-clamp-none">
                        {item.published_at
                          ? new Date(item.published_at).toLocaleString(
                              "zh-CN",
                              {
                                timeZone: "Asia/Shanghai",
                              },
                            )
                          : "发布时间未知"}
                      </ItemDescription>
                      {safeExternalHref(item.url) ? (
                        <a
                          href={safeExternalHref(item.url)!}
                          target="_blank"
                          rel="noreferrer"
                          className="break-all underline underline-offset-4"
                        >
                          {item.url}
                        </a>
                      ) : (
                        <p className="break-all">{item.url}</p>
                      )}
                      <p className="break-words whitespace-pre-wrap">
                        {item.excerpt}
                      </p>
                    </ItemContent>
                  </article>
                </Item>
              ))}
            </div>
          ) : null}
        </ItemContent>
      </section>
    </Item>
  );
}
