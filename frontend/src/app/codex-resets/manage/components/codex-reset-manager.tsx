"use client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { toast } from "sonner";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";

import Link from "next/link";
import { useId, useEffect, useRef, useState } from "react";
import {
  configureCodexResetMonitor,
  correctCodexResetEvent,
  getCodexResetConfiguration,
  getCodexResetSnapshot,
  listCodexResetPosts,
  listCodexResetScanGaps,
  pollCodexResetMonitor,
  relinkCodexResetPost,
  reviewCodexResetPost,
  reviewCodexResetScanGap,
} from "@/api/zhongzhigonggao";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

export function CodexResetManager() {
  const fieldId = useId();

  const [monitor, setMonitor] = useState<HotKeyAPI.MonitorView | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [token, setToken] = useState("");
  const [configuration, setConfiguration] =
    useState<HotKeyAPI.MonitorConfiguration>({
      author: "thsottiaux",
      source_key: "x",
      normal_interval_seconds: 300,
      hot_interval_seconds: 180,
      max_pages: 5,
    });
  const [enabled, setEnabled] = useState(false);
  const [reason, setReason] = useState("");
  const [posts, setPosts] = useState<HotKeyAPI.ResetPostView[]>([]);
  const [gaps, setGaps] = useState<HotKeyAPI.ScanGapView[]>([]);
  const [events, setEvents] = useState<HotKeyAPI.ResetEventView[]>([]);
  const [page, setPage] = useState(1);
  const [event, setEvent] = useState<HotKeyAPI.ResetEventView | null>(null);
  const [patch, setPatch] = useState("{}");
  const [receiptDate, setReceiptDate] = useState("");
  const [receiptTime, setReceiptTime] = useState("");
  const [lookback, setLookback] = useState(24);
  const [job, setJob] = useState<HotKeyAPI.JobView | null>(null);
  const [busy, setBusy] = useState(false);

  const [relinkPost, setRelinkPost] = useState<HotKeyAPI.ResetPostView | null>(
    null,
  );
  const [relinkSource, setRelinkSource] =
    useState<HotKeyAPI.ResetEventView | null>(null);
  const [relinkTarget, setRelinkTarget] =
    useState<HotKeyAPI.ResetEventView | null>(null);
  const context = useRef(0);
  const operations = useRef(new Map<string, string>());
  const headers = { "X-HotKey-Operator-Token": token, "X-HotKey-CSRF": "1" };
  function id(value: object) {
    const key = JSON.stringify(value);
    if (!operations.current.has(key))
      operations.current.set(key, crypto.randomUUID());
    return operations.current.get(key)!;
  }
  function applyMonitor(value: HotKeyAPI.MonitorView | null) {
    setMonitor(value);
    setLoaded(true);
    if (value) {
      setConfiguration(value.configuration);
      setEnabled(value.enabled);
    }
  }
  function changeToken(value: string) {
    context.current += 1;
    operations.current.clear();
    setToken(value);
    setPosts([]);
    setGaps([]);
    setEvents([]);
    setEvent(null);
    setRelinkPost(null);
    setRelinkSource(null);
    setRelinkTarget(null);

    setJob(null);
    setBusy(false);
  }
  useEffect(() => {
    const controller = new AbortController();
    void getCodexResetConfiguration({ signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) applyMonitor(value);
      })
      .catch((cause) => {
        if (cause instanceof ApiRequestError && cause.kind === "cancelled")
          return;
        if (!controller.signal.aborted)
          toast.error(
            cause instanceof ApiRequestError ? cause.message : "配置读取失败。",
          );
      });
    return () => {
      context.current += 1;
      controller.abort();
    };
  }, []);
  async function perform(action: () => Promise<void>, operationId?: string) {
    const epoch = context.current;
    setBusy(true);

    try {
      await action();
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.kind === "cancelled")
        return;
      if (epoch !== context.current) return;
      const message =
        cause instanceof ApiRequestError
          ? cause.message
          : "请求失败，请检查输入或重试读取。";
      const unknown =
        cause instanceof ApiRequestError &&
        ["network", "timeout", "protocol"].includes(cause.kind);
      toast.error(
        `${message}${cause instanceof ApiRequestError && cause.requestId ? ` 请求编号：${cause.requestId}` : ""}${unknown && operationId ? ` 操作结果尚未确认，操作编号：${operationId}。请先重新读取配置与复核状态。` : ""}`,
      );
    } finally {
      if (epoch === context.current) setBusy(false);
    }
  }
  async function read(targetPage = page, epoch = context.current) {
    if (epoch !== context.current) return;
    const current = await getCodexResetConfiguration({ headers });
    if (epoch !== context.current) return;
    applyMonitor(current);
    if (!current) {
      setPosts([]);
      setGaps([]);
      setEvents([]);
      return;
    }
    const [sourcePosts, scanGaps, snapshot] = await Promise.all([
      listCodexResetPosts({ page: targetPage, filter_key: "all" }, { headers }),
      listCodexResetScanGaps({ monitor_id: current.id }, { headers }),
      getCodexResetSnapshot({ include_withdrawn: true }, { headers }),
    ]);
    if (epoch !== context.current) return;
    setPosts(sourcePosts);
    setGaps(scanGaps);
    setEvents(snapshot?.events ?? []);
    setPage(targetPage);
  }
  function relink() {
    if (!monitor || !relinkPost || !relinkSource) return;
    const epoch = context.current;
    const command: HotKeyAPI.CodexPostRelinkInput = {
      from_event_id: relinkSource.id,
      to_event_id: relinkTarget?.id ?? null,
      target_expected_revision: relinkTarget?.revision ?? null,
      review: {
        operation_id: "",
        expected_revision: relinkSource.revision,
        reason: reason.trim(),
        actor: "operator",
      },
    };
    command.review.operation_id = id({
      monitor: monitor.id,
      post: relinkPost.id,
      ...command,
    });
    void perform(async () => {
      await relinkCodexResetPost(
        { monitor_id: monitor.id, post_id: relinkPost.id },
        command,
        { headers },
      );
      if (epoch !== context.current) return;
      await read(page, epoch);
      if (epoch !== context.current) return;
      setRelinkPost(null);
      setRelinkSource(null);
      setRelinkTarget(null);
      toast.success("帖子归属与双方公告修订已保存。");
    }, command.review.operation_id);
  }
  function save() {
    const epoch = context.current;
    const value = {
      expected_revision: monitor?.revision ?? 0,
      reason,
      enabled: monitor ? enabled : false,
      configuration: {
        ...configuration,
        author: "thsottiaux",
        source_key: "x",
      },
    };
    const operationId = id(value);
    void perform(async () => {
      const saved = await configureCodexResetMonitor(
        { ...value, operation_id: operationId },
        { headers },
      );
      if (epoch !== context.current) return;
      if (saved) applyMonitor(saved);
      toast.success("公告配置已保存。真实扫描仍服从来源授权、预算和运行开关。");
    }, operationId);
  }
  function reviewPost(
    post: HotKeyAPI.ResetPostView,
    action: HotKeyAPI.CodexPostReviewInput["action"],
  ) {
    if (!monitor) return;
    const epoch = context.current;
    const value = {
      action,
      review: {
        expected_revision: post.review_version,
        reason,
        actor: "operator",
      },
    };
    const operationId = id({ post: post.id, ...value });
    void perform(async () => {
      await reviewCodexResetPost(
        { monitor_id: monitor.id, post_id: post.id },
        { ...value, review: { ...value.review, operation_id: operationId } },
        { headers },
      );
      if (epoch !== context.current) return;
      await read(page, epoch);
      if (epoch !== context.current) return;
      toast.success(
        "帖子复核已记录。再次识别只会在明确许可与模型准入通过后运行。",
      );
    }, operationId);
  }
  function reviewGap(
    gap: HotKeyAPI.ScanGapView,
    action: HotKeyAPI.CodexGapReviewInput["action"],
  ) {
    if (!monitor) return;
    const epoch = context.current;
    const value = {
      action,
      review: {
        expected_revision: monitor.revision,
        reason,
        actor: "operator",
      },
    };
    const operationId = id({ gap: gap.id, ...value });
    void perform(async () => {
      await reviewCodexResetScanGap(
        { monitor_id: monitor.id, gap_id: gap.id },
        { ...value, review: { ...value.review, operation_id: operationId } },
        { headers },
      );
      if (epoch !== context.current) return;
      await read(page, epoch);
      if (epoch !== context.current) return;
      toast.success("扫描缺口复核已记录。确认缺口不会推进已核验水位。");
    }, operationId);
  }
  function correct(patchValue: HotKeyAPI.EventPatch) {
    if (!monitor || !event) return;
    const epoch = context.current;
    const value = {
      patch: patchValue,
      review: { expected_revision: event.revision, reason, actor: "operator" },
    };
    const operationId = id({ event: event.id, ...value });
    void perform(async () => {
      const result = await correctCodexResetEvent(
        { monitor_id: monitor.id, event_id: event.id },
        { ...value, review: { ...value.review, operation_id: operationId } },
        { headers },
      );
      if (epoch !== context.current) return;
      setEvent(result);
      await read(page, epoch);
      if (epoch !== context.current) return;
      toast.success("公告修订与审计已保存。");
    }, operationId);
  }
  function correctJson() {
    try {
      const value: unknown = JSON.parse(patch);
      if (
        !value ||
        typeof value !== "object" ||
        Array.isArray(value) ||
        Object.keys(value).length === 0
      )
        throw new Error();
      correct(value as HotKeyAPI.EventPatch);
    } catch {
      toast.error("公告修订 JSON 必须是非空对象，日期需显式填写。");
    }
  }
  function receipt() {
    const confirmed = new Date(`${receiptTime}:00+08:00`);
    if (Number.isNaN(confirmed.valueOf())) {
      toast.error("请填写有效的北京时间到账时间。");
      return;
    }
    correct({
      status: "confirmed",
      occurred_on: receiptDate,
      confirmed_at: confirmed.toISOString(),
      confirmation_basis: "receipt_review",
    });
  }
  function poll() {
    if (!monitor) return;
    const epoch = context.current;
    const value = {
      expected_revision: monitor.revision,
      reason,
      lookback_hours: lookback,
    };
    const operationId = id({ monitor: monitor.id, tick: value });
    void perform(async () => {
      const result = await pollCodexResetMonitor(
        { monitor_id: monitor.id },
        { ...value, operation_id: operationId },
        { headers },
      );
      if (epoch !== context.current) return;
      setJob(result);
      toast.success("扫描任务已受理，请查看任务回执。");
    }, operationId);
  }
  const canWrite = !!token && !!reason.trim() && !busy;
  return (
    <div className="flex flex-col gap-y-8">
      <div>
        <h1 className="text-3xl font-medium">公告配置与人工复核</h1>
        <p className="text-muted-foreground mt-3">
          固定官方作者
          thsottiaux。预测日程与确认到账分别记录，未知来源或模型请求需要人工复核。
        </p>
        <Link
          href="/codex-resets"
          className="mt-3 inline-block underline underline-offset-4"
        >
          返回公告日历
        </Link>
      </div>
      <Item variant="muted" asChild>
        <section
          className="flex flex-col gap-y-4 p-5"
          aria-label="运营权限与原因"
        >
          <ItemContent className="min-w-0 gap-3">
            <Label htmlFor="codex-operator">操作员令牌</Label>
            <Input
              id="codex-operator"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => changeToken(e.target.value)}
            />
            <ItemDescription className="line-clamp-none">
              令牌仅用于当前页面内存。服务端未配置权限时，写入保持关闭。
            </ItemDescription>
            <Label htmlFor="codex-reason">操作与复核原因</Label>
            <Textarea
              id="codex-reason"
              value={reason}
              maxLength={2000}
              onChange={(e) => setReason(e.target.value)}
            />
            <div className="flex flex-wrap gap-3">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() =>
                  void perform(async () =>
                    applyMonitor(await getCodexResetConfiguration()),
                  )
                }
              >
                重读配置
              </Button>
              <Button
                disabled={!token || busy}
                onClick={() => void perform(() => read())}
              >
                读取待复核与公告
              </Button>
              <Button variant="ghost" onClick={() => changeToken("")}>
                清除令牌
              </Button>
            </div>
          </ItemContent>
        </section>
      </Item>
      <section className="flex flex-col gap-y-5" aria-label="官方监控配置">
        <h2 className="text-xl font-medium">
          {monitor
            ? `监控修订 ${monitor.revision} · 配置版本 ${monitor.configuration_version}`
            : loaded
              ? "尚未配置公告监控"
              : "正在读取配置…"}
        </h2>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field className="flex flex-col gap-y-2">
            <FieldLabel htmlFor="codex-author-id">官方作者外部 ID</FieldLabel>
            <Input
              id="codex-author-id"
              value={configuration.author_external_id ?? ""}
              maxLength={128}
              onChange={(e) =>
                setConfiguration({
                  ...configuration,
                  author_external_id: e.target.value || null,
                })
              }
            />
          </Field>
          <Field className="flex flex-col gap-y-2">
            <FieldLabel htmlFor="codex-connection">
              批准的官方 X 连接 ID
            </FieldLabel>
            <Input
              id="codex-connection"
              value={configuration.connection_id ?? ""}
              onChange={(e) =>
                setConfiguration({
                  ...configuration,
                  connection_id: e.target.value || null,
                })
              }
            />
          </Field>
          <Field className="flex flex-col gap-y-2">
            <FieldLabel htmlFor="codex-connection-version">连接版本</FieldLabel>
            <Input
              id="codex-connection-version"
              type="number"
              min={1}
              value={configuration.connection_version ?? 1}
              onChange={(e) =>
                setConfiguration({
                  ...configuration,
                  connection_version: Number(e.target.value),
                })
              }
            />
          </Field>
          <Field className="flex flex-col gap-y-2">
            <FieldLabel htmlFor="codex-max-pages">单轮新帖子页上限</FieldLabel>
            <Input
              id="codex-max-pages"
              type="number"
              min={1}
              max={5}
              value={configuration.max_pages ?? 5}
              onChange={(e) =>
                setConfiguration({
                  ...configuration,
                  max_pages: Number(e.target.value),
                })
              }
            />
          </Field>
          <Field className="flex flex-col gap-y-2">
            <FieldLabel htmlFor="codex-normal">正常扫描间隔（秒）</FieldLabel>
            <Input
              id="codex-normal"
              type="number"
              min={60}
              value={configuration.normal_interval_seconds ?? 300}
              readOnly
            />
          </Field>
          <Field className="flex flex-col gap-y-2">
            <FieldLabel htmlFor="codex-hot">临近公告扫描间隔（秒）</FieldLabel>
            <Input
              id="codex-hot"
              type="number"
              min={60}
              value={configuration.hot_interval_seconds ?? 180}
              readOnly
            />
          </Field>
        </div>
        {monitor && (
          <Field orientation="horizontal" className="w-auto">
            <Checkbox
              checked={enabled}
              onCheckedChange={(checked) => setEnabled(checked === true)}
              id={`${fieldId}-codex-reset-manager-field-1`}
            />
            <FieldLabel htmlFor={`${fieldId}-codex-reset-manager-field-1`}>
              启用公告监控（仍需真实授权与预算）
            </FieldLabel>
          </Field>
        )}
        <Button disabled={!canWrite || !loaded} onClick={save}>
          {monitor ? "保存公告配置" : "创建关闭公告监控"}
        </Button>
        <p className="text-muted-foreground text-sm">
          首次创建保持关闭。X
          凭据、付费预算与模型开关由服务端批准，配置保存不会发起外部请求。
        </p>
      </section>
      {monitor && (
        <section className="flex flex-col gap-y-4" aria-label="人工扫描">
          <h2 className="text-xl font-medium">人工受理扫描</h2>
          <Label htmlFor="codex-lookback">回看小时数</Label>
          <Input
            id="codex-lookback"
            type="number"
            min={1}
            max={168}
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
          />
          <Button disabled={!canWrite || !monitor.enabled} onClick={poll}>
            受理一次公告扫描
          </Button>
          {job && (
            <Alert role="status">
              <AlertDescription>
                任务已受理：
                <Link
                  href={`/jobs/${job.id}`}
                  className="underline underline-offset-4"
                >
                  查看任务 {job.id}
                </Link>
              </AlertDescription>
            </Alert>
          )}
        </section>
      )}
      {!!gaps.length && (
        <section
          className="flex flex-col gap-y-4"
          aria-label="分页积压与未知请求"
        >
          <h2 className="text-xl font-medium">扫描缺口</h2>
          {gaps.map((gap) => (
            <Item variant="muted" key={gap.id} asChild>
              <article className="flex flex-col gap-y-3 p-5">
                <ItemContent className="min-w-0 gap-3">
                  <p className="break-words">
                    {gap.state} · {gap.failure_code ?? "未完成窗口"} · 配置版本{" "}
                    {gap.configuration_version}
                  </p>
                  <ItemDescription className="line-clamp-none break-all">
                    查询 {gap.query} ·{" "}
                    {gap.has_resume_token ? "已保留分页凭证" : "无分页凭证"}
                  </ItemDescription>
                  {gap.state !== "complete" && (
                    <div className="flex flex-wrap gap-3">
                      <Button
                        variant="outline"
                        disabled={!canWrite}
                        onClick={() => reviewGap(gap, "retry")}
                      >
                        允许恢复此窗口
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={!canWrite}
                        onClick={() => reviewGap(gap, "acknowledge")}
                      >
                        确认此缺口
                      </Button>
                    </div>
                  )}
                </ItemContent>
              </article>
            </Item>
          ))}
        </section>
      )}
      {monitor && (
        <section className="flex flex-col gap-y-4" aria-label="帖子复核">
          <h2 className="text-xl font-medium">源帖子复核 · 第 {page} 页</h2>
          {posts.map((post) => (
            <Item variant="muted" key={post.id} asChild>
              <article className="flex flex-col gap-y-3 p-5">
                <ItemContent className="min-w-0 gap-3">
                  <p className="break-words whitespace-pre-wrap">{post.text}</p>
                  <ItemDescription className="line-clamp-none">
                    复核版本 {post.review_version} ·{" "}
                    {post.failure_code ?? (post.reviewed ? "已复核" : "待处理")}{" "}
                    · 失败 {post.failure_count}
                  </ItemDescription>
                  <a
                    href={post.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm underline underline-offset-4"
                  >
                    官方原帖
                  </a>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      variant="outline"
                      disabled={!canWrite}
                      onClick={() => reviewPost(post, "reviewed")}
                    >
                      标记已复核
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={!canWrite}
                      onClick={() => reviewPost(post, "skip")}
                    >
                      跳过此帖子
                    </Button>
                    {post.needs_review && (
                      <Button
                        disabled={!canWrite}
                        onClick={() => reviewPost(post, "retry")}
                      >
                        明确允许再次识别
                      </Button>
                    )}
                    {!!post.event_ids?.some((eventId) =>
                      events.some((item) => item.id === eventId),
                    ) && (
                      <Button
                        variant="outline"
                        disabled={!token || busy}
                        onClick={() => {
                          setRelinkPost(post);
                          setRelinkSource(
                            events.find((item) =>
                              post.event_ids?.includes(item.id),
                            ) ?? null,
                          );
                          setRelinkTarget(null);
                        }}
                      >
                        更改公告归属
                      </Button>
                    )}
                  </div>
                </ItemContent>
              </article>
            </Item>
          ))}
          <div className="flex gap-3">
            <Button
              variant="outline"
              disabled={busy || !token || page <= 1}
              onClick={() => void perform(() => read(page - 1))}
            >
              上一页帖子
            </Button>
            <Button
              variant="outline"
              disabled={busy || !token || posts.length < 50}
              onClick={() => void perform(() => read(page + 1))}
            >
              下一页帖子
            </Button>
          </div>
        </section>
      )}
      {relinkPost && relinkSource && (
        <Item variant="muted" asChild>
          <section
            className="flex flex-col gap-y-4 p-5"
            aria-label="帖子公告归属"
          >
            <ItemContent className="min-w-0 gap-3">
              <ItemTitle className="line-clamp-none w-full">
                <h2>更改帖子公告归属</h2>
              </ItemTitle>
              <p className="text-sm leading-7">
                帖子 {relinkPost.external_id}
                ；两份公告均按打开表单时的修订提交。版本冲突后请重读并重新打开，不自动覆盖。
              </p>
              <Label htmlFor="codex-relink-source">原公告</Label>
              <Select
                value={relinkSource.id}
                disabled={busy}
                onValueChange={(selectedValue) => {
                  setRelinkSource(
                    events.find((item) => item.id === selectedValue) ?? null,
                  );
                  setRelinkTarget(null);
                }}
              >
                <SelectTrigger
                  id="codex-relink-source"
                  className="w-full min-w-0"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">原公告</SelectLabel>
                    {events
                      .filter((item) => relinkPost.event_ids?.includes(item.id))
                      .map((item) => (
                        <SelectItem
                          key={item.id}
                          value={item.id}
                          className="whitespace-normal"
                        >
                          {item.title || item.id} · 修订 {item.revision}
                        </SelectItem>
                      ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <p className="text-sm">原公告预期修订 {relinkSource.revision}</p>
              <Label htmlFor="codex-relink-target">目标公告</Label>
              <Select
                value={relinkTarget?.id ?? ""}
                disabled={busy}
                onValueChange={(selectedValue) =>
                  setRelinkTarget(
                    events.find(
                      (item) =>
                        item.id ===
                        (selectedValue === "__none__" ? "" : selectedValue),
                    ) ?? null,
                  )
                }
              >
                <SelectTrigger
                  id="codex-relink-target"
                  className="w-full min-w-0"
                >
                  <SelectValue placeholder="解除此公告关联（不归入其他公告）" />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">原公告</SelectLabel>
                    <SelectItem value="__none__" className="whitespace-normal">
                      解除此公告关联（不归入其他公告）
                    </SelectItem>
                    {events
                      .filter((item) => item.id !== relinkSource.id)
                      .map((item) => (
                        <SelectItem
                          key={item.id}
                          value={item.id}
                          className="whitespace-normal"
                        >
                          {item.title || item.id} · 修订 {item.revision}
                        </SelectItem>
                      ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <p className="text-sm">
                {relinkTarget
                  ? `目标公告预期修订 ${relinkTarget.revision}`
                  : "目标公告与目标修订均为空；仅解除原关联。"}
              </p>
              <ItemDescription className="line-clamp-none">
                使用上方复核原因记录审计。此操作只修正帖子关联，不调用模型，不确认到账。
              </ItemDescription>
              <div className="flex gap-3">
                <Button disabled={!canWrite} onClick={relink}>
                  保存帖子归属
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => setRelinkPost(null)}
                >
                  关闭归属表单
                </Button>
              </div>
            </ItemContent>
          </section>
        </Item>
      )}
      {!!events.length && (
        <section
          className="flex flex-col gap-y-4"
          aria-label="公告日期与到账复核"
        >
          <h2 className="text-xl font-medium">公告日期与到账复核</h2>
          {events.map((item) => (
            <Item variant="muted" key={item.id} asChild>
              <article className="flex flex-col gap-y-3 p-5">
                <ItemContent className="min-w-0 gap-3">
                  <p>
                    {item.title ?? item.kind} · {item.status} · 修订{" "}
                    {item.revision}· {item.withdrawn ? "已撤回" : "有效"}
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEvent(item);
                      setPatch(JSON.stringify({ kind: item.kind }, null, 2));
                      setReceiptDate(item.occurred_on ?? "");
                      setReceiptTime("");
                    }}
                  >
                    修订此公告
                  </Button>
                </ItemContent>
              </article>
            </Item>
          ))}
        </section>
      )}
      {event && (
        <section className="flex flex-col gap-y-5" aria-label="公告修订表单">
          <h2 className="text-xl font-medium">
            修订公告 · 预期版本 {event.revision}
          </h2>
          <Label htmlFor="codex-event-json">公告修订 JSON</Label>
          <Textarea
            id="codex-event-json"
            className="min-h-40 font-mono text-sm"
            value={patch}
            maxLength={65536}
            onChange={(e) => setPatch(e.target.value)}
          />
          <p className="text-muted-foreground text-sm">
            支持类型、明确日程与范围；时间填写带时区的 ISO
            值。人工修改不会自动确认到账。
          </p>
          <div className="flex flex-wrap gap-3">
            <Button disabled={!canWrite} onClick={correctJson}>
              保存公告修订
            </Button>
            <Button
              variant="outline"
              disabled={!canWrite}
              onClick={() => correct({ withdrawn: !event.withdrawn })}
            >
              {event.withdrawn ? "恢复撤回公告" : "撤回此公告"}
            </Button>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field className="flex flex-col gap-y-2">
              <FieldLabel htmlFor="codex-receipt-date">
                人工核验到账日期（北京）
              </FieldLabel>
              <Input
                id="codex-receipt-date"
                type="date"
                value={receiptDate}
                onChange={(e) => setReceiptDate(e.target.value)}
              />
            </Field>
            <Field className="flex flex-col gap-y-2">
              <FieldLabel htmlFor="codex-receipt-time">
                人工核验到账时间（北京）
              </FieldLabel>
              <Input
                id="codex-receipt-time"
                type="datetime-local"
                value={receiptTime}
                onChange={(e) => setReceiptTime(e.target.value)}
              />
            </Field>
          </div>
          <Button
            disabled={!canWrite || !receiptDate || !receiptTime}
            onClick={receipt}
          >
            保存人工到账核验
          </Button>
        </section>
      )}
    </div>
  );
}
