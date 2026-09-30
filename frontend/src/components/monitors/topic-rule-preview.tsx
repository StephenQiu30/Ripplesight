"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LoaderCircleIcon, SearchCheckIcon } from "lucide-react";

import {
  previewMonitorTopic,
  previewMonitorTopicSamples,
} from "@/api/jiankongzhuti";
import { parseKeywordLines } from "@/components/monitors/keyword-group-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

type TopicRulePreviewProps = {
  matchAny: string;
  matchAll: string;
  exclude: string;
  sourceKeys?: string[];
  disabled?: boolean;
};

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; preview: HotKeyAPI.MonitorTopicPreviewView }
  | { status: "error"; message: string; requestId?: string };

type SampleState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; preview: HotKeyAPI.ContentSamplePreviewView }
  | { status: "error"; message: string; requestId?: string };

export function TopicRulePreview(props: TopicRulePreviewProps) {
  return (
    <TopicRulePreviewDialog
      key={JSON.stringify([
        props.matchAny,
        props.matchAll,
        props.exclude,
        props.sourceKeys,
      ])}
      {...props}
    />
  );
}

function TopicRulePreviewDialog({
  matchAny,
  matchAll,
  exclude,
  sourceKeys = [],
  disabled = false,
}: TopicRulePreviewProps) {
  const router = useRouter();
  const [sampleTitle, setSampleTitle] = useState("");
  const [state, setState] = useState<PreviewState>({ status: "idle" });
  const [sampleState, setSampleState] = useState<SampleState>({
    status: "idle",
  });
  const submittingRef = useRef(false);
  const sampleSubmittingRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function handleSamplePreview() {
    if (sampleSubmittingRef.current) return;
    if (
      parseKeywordLines(matchAny).length === 0 &&
      parseKeywordLines(matchAll).length === 0
    ) {
      setSampleState({ status: "error", message: "至少填写一个包含关键词。" });
      return;
    }
    sampleSubmittingRef.current = true;
    setSampleState({ status: "loading" });
    try {
      const preview = await previewMonitorTopicSamples({
        match_any: parseKeywordLines(matchAny),
        match_all: parseKeywordLines(matchAll),
        exclude: parseKeywordLines(exclude),
        source_keys: sourceKeys,
      });
      if (mountedRef.current) setSampleState({ status: "ready", preview });
    } catch (error) {
      if (!mountedRef.current) return;
      if (
        error instanceof ApiRequestError &&
        error.code === "invalid_session"
      ) {
        router.replace("/login");
        return;
      }
      setSampleState({
        status: "error",
        message:
          error instanceof ApiRequestError
            ? error.message
            : "样本预览失败，请重试。",
        requestId:
          error instanceof ApiRequestError ? error.requestId : undefined,
      });
    } finally {
      sampleSubmittingRef.current = false;
    }
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (submittingRef.current) return;
    const any = parseKeywordLines(matchAny);
    const all = parseKeywordLines(matchAll);
    if (any.length === 0 && all.length === 0) {
      setState({
        status: "error",
        message: "至少填写一个“任意命中”或“全部包含”关键词。",
      });
      return;
    }

    submittingRef.current = true;
    setState({ status: "loading" });
    try {
      const preview = await previewMonitorTopic({
        match_any: any,
        match_all: all,
        exclude: parseKeywordLines(exclude),
        sample_titles: [sampleTitle],
      });
      if (mountedRef.current) {
        setState({ status: "ready", preview });
      }
    } catch (error) {
      if (!mountedRef.current) return;
      if (
        error instanceof ApiRequestError &&
        error.code === "invalid_session"
      ) {
        router.replace("/login");
        return;
      }
      setState({
        status: "error",
        message:
          error instanceof ApiRequestError
            ? error.status === 422 && error.details?.[0]
              ? error.details[0].message
              : error.message
            : "规则预览失败，请稍后重试。",
        requestId:
          error instanceof ApiRequestError ? error.requestId : undefined,
      });
    } finally {
      submittingRef.current = false;
    }
  }

  const sample = state.status === "ready" ? state.preview.samples[0] : null;
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="secondary"
          className="w-full"
          disabled={disabled}
        >
          <SearchCheckIcon data-icon="inline-start" />
          预览规则
        </Button>
      </DialogTrigger>
      <DialogContent
        className="max-h-dvh max-w-lg overflow-y-auto"
        showCloseButton={false}
      >
        <DialogHeader>
          <DialogTitle>本地规则预览</DialogTitle>
          <DialogDescription>
            检查草稿关键词，或查看已有内容的匹配情况。预览不会保存主题、创建任务或访问外部来源。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Button
            type="button"
            variant="secondary"
            onClick={handleSamplePreview}
            disabled={disabled || sampleState.status === "loading"}
          >
            {sampleState.status === "loading" ? (
              <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
            ) : (
              <SearchCheckIcon aria-hidden="true" />
            )}
            {sampleState.status === "loading"
              ? "正在读取样本"
              : "预览已采集内容"}
          </Button>
          <p className="text-muted-foreground text-xs leading-5">
            读取所选来源最近 7 天的最多 20
            条可读内容；未选择来源时读取全部已有来源。包含未命中与排除样本，只说明本地草稿匹配。
          </p>
          {sampleState.status === "error" ? (
            <div
              role="alert"
              className="bg-destructive/10 rounded-lg p-3 text-sm"
            >
              <p>{sampleState.message}</p>
              {sampleState.requestId ? (
                <p className="mt-1 text-xs">
                  请求编号：{sampleState.requestId}
                </p>
              ) : null}
            </div>
          ) : null}
          {sampleState.status === "ready" ? (
            <div className="space-y-3" aria-live="polite">
              <p className="text-muted-foreground text-xs leading-5">
                {new Date(sampleState.preview.starts_at).toLocaleString(
                  "zh-CN",
                  { timeZone: "Asia/Shanghai" },
                )}{" "}
                至{" "}
                {new Date(sampleState.preview.ends_at).toLocaleString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                })}
                （上海时间） · {sampleState.preview.samples.length} 条样本
                {sampleState.preview.truncated ? "，仅展示最新 20 条" : ""} ·
                未保存的草稿规则
              </p>
              <p className="text-muted-foreground text-xs">
                规范化规则：任一{" "}
                {sampleState.preview.rules.match_any.join("、") || "不限制"}
                ；全部{" "}
                {sampleState.preview.rules.match_all.join("、") || "不限制"}
                ；排除 {sampleState.preview.rules.exclude.join("、") || "无"}
              </p>
              {sampleState.preview.sample_status === "insufficient_samples" ? (
                <p role="status" className="bg-muted rounded-lg p-3 text-sm">
                  预览证据不足：此时间窗与来源下没有可读样本。不能据此判断源站无结果或规则无效。
                </p>
              ) : (
                sampleState.preview.samples.map((item) => (
                  <article
                    key={item.observation_id}
                    className="bg-muted space-y-2 rounded-xl p-4 text-sm"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={item.matched ? "secondary" : "outline"}>
                        {item.excluded_by.length
                          ? "已排除"
                          : item.matched
                            ? "命中"
                            : "未命中"}
                      </Badge>
                      <span className="text-muted-foreground text-xs">
                        {item.source_key} · 观察于{" "}
                        {new Date(item.observed_at).toLocaleString("zh-CN", {
                          timeZone: "Asia/Shanghai",
                        })}
                      </span>
                    </div>
                    <Link
                      href={`/content/${item.content_id}`}
                      className="font-medium break-words underline underline-offset-4"
                    >
                      {item.title || "查看正文样本"}
                    </Link>
                    {item.body_excerpt ? (
                      <p className="text-muted-foreground break-words whitespace-pre-wrap">
                        {item.body_excerpt}
                      </p>
                    ) : null}
                    {item.excerpt_truncated ? (
                      <p className="text-muted-foreground text-xs">
                        摘录已截断；匹配依据为完整已保存文字。
                      </p>
                    ) : null}
                    <p className="text-xs leading-5">
                      任一命中：{item.matched_any.join("、") || "无"}
                      ；全部命中：{item.matched_all.join("、") || "无"}
                      ；排除命中：{item.excluded_by.join("、") || "无"}
                    </p>
                    <p className="text-muted-foreground text-xs break-all">
                      内容版本：{item.content_version_id}
                    </p>
                  </article>
                ))
              )}
            </div>
          ) : null}
        </div>

        <form className="space-y-4" onSubmit={handlePreview}>
          <div className="space-y-2">
            <Label htmlFor="preview-sample-title">标题样本</Label>
            <Textarea
              id="preview-sample-title"
              value={sampleTitle}
              onChange={(event) => setSampleTitle(event.target.value)}
              maxLength={500}
              required
              placeholder="例如：AI Agent 开源模型发布"
            />
          </div>
          <Button type="submit" disabled={state.status === "loading"}>
            {state.status === "loading" ? (
              <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
            ) : (
              <SearchCheckIcon data-icon="inline-start" />
            )}
            {state.status === "loading" ? "正在检查" : "检查标题"}
          </Button>
        </form>

        {state.status === "error" ? (
          <div
            className="bg-destructive/10 rounded-lg p-3 text-sm"
            role="alert"
          >
            <p>{state.message}</p>
            {state.requestId ? (
              <p className="mt-1 font-mono text-xs">
                请求编号：{state.requestId}
              </p>
            ) : null}
          </div>
        ) : null}

        {state.status === "ready" && sample ? (
          <div className="space-y-4" aria-live="polite">
            <div className="bg-muted rounded-xl p-4">
              <div className="flex items-center gap-2">
                <Badge variant={sample.matched ? "secondary" : "outline"}>
                  {sample.matched
                    ? "命中"
                    : sample.excluded_by.length > 0
                      ? "已排除"
                      : "未命中"}
                </Badge>
                {sample.excluded_by.length > 0 ? (
                  <span className="text-muted-foreground text-xs">
                    排除原因：{sample.excluded_by.join("、")}
                  </span>
                ) : null}
              </div>
              <dl className="text-muted-foreground mt-4 space-y-2 text-xs leading-5">
                <div>
                  <dt className="text-foreground font-medium">本次任意命中</dt>
                  <dd>{sample.matched_any.join("、") || "无"}</dd>
                </div>
                <div>
                  <dt className="text-foreground font-medium">
                    本次全部包含命中
                  </dt>
                  <dd>
                    {state.preview.rules.match_all.length === 0
                      ? "未配置（不限制）"
                      : `${sample.matched_all.join("、") || "无"}；命中 ${sample.matched_all.length}/${state.preview.rules.match_all.length} 项`}
                  </dd>
                </div>
              </dl>
              <dl className="text-muted-foreground mt-4 space-y-2 text-xs leading-5">
                <div>
                  <dt className="text-foreground font-medium">任意命中</dt>
                  <dd>
                    {state.preview.rules.match_any.join("、") || "不限制"}
                  </dd>
                </div>
                <div>
                  <dt className="text-foreground font-medium">全部包含</dt>
                  <dd>
                    {state.preview.rules.match_all.join("、") || "不限制"}
                  </dd>
                </div>
                <div>
                  <dt className="text-foreground font-medium">排除优先</dt>
                  <dd>{state.preview.rules.exclude.join("、") || "无"}</dd>
                </div>
              </dl>
            </div>

            <div className="ring-foreground/10 rounded-xl p-4 text-sm ring-1">
              <p className="font-medium">查询与预算影响</p>
              <p className="text-muted-foreground mt-2 leading-6">
                本地别名匹配：
                {state.preview.expansion.local_alias_external_queries}
                次外部查询，
                {state.preview.expansion.local_alias_budget_units}
                预算单位。
              </p>
              <p className="text-muted-foreground mt-1 leading-6">
                上游扩词：
                {sourceKeys.length === 0 ? "来源尚未选择" : "尚未核实"}
                ，查询次数
                {state.preview.expansion.upstream_external_queries ?? "未知"}
                ，预算
                {state.preview.expansion.upstream_budget_units ?? "未知"}
                ，当前不能启用。
              </p>
            </div>
          </div>
        ) : null}
        <DialogClose asChild>
          <Button type="button" variant="ghost" className="justify-self-end">
            关闭预览
          </Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}
