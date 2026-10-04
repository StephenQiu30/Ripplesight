"use client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import { Field, FieldLabel } from "@/components/ui/field";

import Link from "next/link";
import { useId, useRef, useState, useEffect } from "react";
import {
  createEditorialSourceProfile,
  getEditorialSourceIcon,
  refreshEditorialSourceIcon,
  listEditorialSourceProfiles,
  listEditorialSourceGroupBacklogs,
  listEditorialSourceRuns,
  pollEditorialSource,
  reviewEditorialSourceRun,
  reviewEditorialSourceGroupBacklog,
  updateEditorialSourceProfile,
} from "@/api/bianjilaiyuan";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";
import { EditorialSourcePreview } from "./editorial-source-preview";
import { EditorialSourceMaterials } from "./editorial-source-materials";
import { EditorialExternalIngress } from "./editorial-external-ingress";
import { EditorialLocalApproval } from "./editorial-local-approval";

const kinds: [HotKeyAPI.EditorialSourceKind, string][] = [
  ["rss", "RSS / Atom"],
  ["web_list", "网页列表"],
  ["json_list", "JSON 列表"],
  ["x_search", "X 官方搜索"],
  ["mp_account", "公众号"],
  ["external", "外部摄入"],
];
const templates: Record<
  HotKeyAPI.EditorialSourceKind,
  HotKeyAPI.EditorialSourceConfiguration
> = {
  rss: {
    kind: "rss",
    feed_url: "https://example.com/feed",
    allowed_hosts: ["example.com"],
  },
  web_list: {
    kind: "web_list",
    url: "https://example.com/news",
    allowed_hosts: ["example.com"],
    item_selector: "article",
    link_selector: "a",
    title_selector: "h2",
  },
  json_list: {
    kind: "json_list",
    url: "https://example.com/news.json",
    allowed_hosts: ["example.com"],
    items_path: "items",
    title_paths: ["title"],
    url_template: "{raw:url}",
  },
  x_search: { kind: "x_search", query: "from:OpenAI", search_type: "Latest" },
  mp_account: { kind: "mp_account", wxid: "请填写公开账号标识" },
  external: { kind: "external" },
};
const time = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
    : "暂无";

export function EditorialSourceManager() {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

  const [token, setToken] = useState("");
  const [previewEpoch, setPreviewEpoch] = useState(0);
  const [profiles, setProfiles] = useState<
    HotKeyAPI.EditorialProfileView[] | null
  >(null);
  const [selected, setSelected] =
    useState<HotKeyAPI.EditorialProfileView | null>(null);
  const [editing, setEditing] = useState(false);
  const [formProfileId, setFormProfileId] = useState<string | null>(null);
  const [formRevision, setFormRevision] = useState(0);
  const [kind, setKind] = useState<HotKeyAPI.EditorialSourceKind>("rss");
  const [name, setName] = useState("");
  const [config, setConfig] = useState(JSON.stringify(templates.rss, null, 2));
  const [mode, setMode] = useState<HotKeyAPI.ParticipationMode>("editorial");
  const [tier, setTier] =
    useState<NonNullable<HotKeyAPI.EditorialProfileInput["tier"]>>("T3");
  const [firstParty, setFirstParty] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [policy, setPolicy] = useState(1);
  const [interval, setInterval] = useState(30);
  const [connection, setConnection] = useState("");
  const [connectionVersion, setConnectionVersion] = useState(1);
  const [reason, setReason] = useState("");
  const [reviewReason, setReviewReason] = useState("");
  const [iconReason, setIconReason] = useState("");
  const [icon, setIcon] = useState<HotKeyAPI.SourceIconView | null>(null);
  const [runs, setRuns] = useState<HotKeyAPI.EditorialRunResult[]>([]);
  const [groups, setGroups] = useState<HotKeyAPI.EditorialGroupBacklogView[]>(
    [],
  );
  const [groupReason, setGroupReason] = useState("");
  const [job, setJob] = useState<HotKeyAPI.JobView | null>(null);
  const [busy, setBusy] = useState(false);

  const operations = useRef(new Map<string, string>());
  const headers = { "X-HotKey-Operator-Token": token, "X-HotKey-CSRF": "1" };
  function operation(value: object) {
    const key = JSON.stringify(value);
    if (!operations.current.has(key))
      operations.current.set(key, crypto.randomUUID());
    return operations.current.get(key)!;
  }
  async function perform(action: () => Promise<void>, operationId?: string) {
    setBusy(true);

    try {
      await action();
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.kind === "cancelled")
        return;
      const message =
        cause instanceof ApiRequestError
          ? cause.code === "editorial_version_conflict"
            ? "来源配置版本已更新，请重新读取并重新打开表单。"
            : cause.message
          : "请求失败，请检查输入或重试读取。";
      const unknown =
        cause instanceof ApiRequestError &&
        ["network", "timeout", "protocol"].includes(cause.kind);
      if (mounted.current)
        toast.error(
          `${message}${cause instanceof ApiRequestError && cause.requestId ? ` 请求编号：${cause.requestId}` : ""}${unknown && operationId ? ` 本次受理结果尚未确认，操作编号：${operationId}。请先读取来源运行记录。` : ""}`,
        );
    } finally {
      setBusy(false);
    }
  }
  async function reload() {
    const value = await listEditorialSourceProfiles({ headers });
    setProfiles(value);
    setGroups(await listEditorialSourceGroupBacklogs({ headers }));
    if (selected) setSelected(value.find((p) => p.id === selected.id) ?? null);
  }
  function restartGroup(group: HotKeyAPI.EditorialGroupBacklogView) {
    const body = {
      group_sha256: group.group_sha256,
      reason: groupReason,
      actor: "Workspace operator",
      action: "restart_from_saved_watermark" as const,
      expected_members: group.members.map((member) => ({
        profile_id: member.profile_id,
        revision: member.revision,
        configuration_version: member.configuration_version,
      })),
    };
    const operationId = operation(body);
    void perform(async () => {
      await reviewEditorialSourceGroupBacklog(
        { ...body, operation_id: operationId },
        { headers },
      );
      await reload();
      if (mounted.current)
        toast.success(
          "原分组积压已复核并退回保存水位。旧成功时钟保留，采集仍需当前许可和各成员预算。",
        );
    }, operationId);
  }
  function edit(profile: HotKeyAPI.EditorialProfileView | null) {
    setSelected(profile);
    setEditing(true);
    setFormProfileId(profile?.id ?? null);
    setFormRevision(profile?.revision ?? 0);
    setRuns([]);
    setIcon(null);
    setIconReason("");
    if (profile)
      void perform(async () =>
        setIcon(
          await getEditorialSourceIcon({ profile_id: profile.id }, { headers }),
        ),
      );
    setJob(null);
    setReason("");
    setName(profile?.name ?? "");
    setKind(profile?.configuration.kind ?? "rss");
    setConfig(JSON.stringify(profile?.configuration ?? templates.rss, null, 2));
    setMode(profile?.participation_mode ?? "editorial");
    setTier(profile?.tier ?? "T3");
    setFirstParty(profile?.first_party ?? false);
    setEnabled(profile?.enabled ?? false);
    setPolicy(profile?.policy_version ?? 1);
    setInterval(profile?.interval_minutes ?? 30);
    setConnection(profile?.connection_id ?? "");
    setConnectionVersion(profile?.connection_version ?? 1);
  }
  function refreshIcon() {
    if (!selected) return;
    const value: Omit<HotKeyAPI.SourceIconRefreshInput, "operation_id"> = {
      expected_revision: formRevision,
      reason: iconReason,
      action: icon?.status === "unknown" ? "retry_unknown" : "refresh",
    };
    const id = operation({ icon: selected.id, ...value });
    void perform(async () => {
      setJob(
        await refreshEditorialSourceIcon(
          { profile_id: selected.id },
          { ...value, operation_id: id },
          { headers },
        ),
      );
      setIcon(
        await getEditorialSourceIcon({ profile_id: selected.id }, { headers }),
      );
      if (mounted.current)
        toast.success(
          "图标任务已受理。仍需独立MEDIA许可与预算，真实外采默认关闭。",
        );
    }, id);
  }
  function save() {
    let configuration: HotKeyAPI.EditorialSourceConfiguration;
    try {
      const value: unknown = JSON.parse(config);
      if (
        !value ||
        typeof value !== "object" ||
        !("kind" in value) ||
        value.kind !== kind
      )
        throw new Error();
      configuration = value as HotKeyAPI.EditorialSourceConfiguration;
    } catch {
      if (mounted.current) toast.error("配置 JSON 必须是对应来源类型的对象。");
      return;
    }
    const value: Omit<HotKeyAPI.EditorialProfileInput, "operation_id"> = {
      expected_revision: formRevision,
      name,
      reason,
      enabled: formProfileId ? enabled : false,
      configuration,
      participation_mode: mode,
      tier,
      first_party: firstParty,
      connection_id: connection || null,
      connection_version: connection ? connectionVersion : null,
      policy_version: policy,
      interval_minutes: interval,
    };
    const id = operation({ profile: formProfileId, ...value });
    void perform(async () => {
      if (formProfileId)
        await updateEditorialSourceProfile(
          { profile_id: formProfileId },
          { ...value, operation_id: id },
          { headers },
        );
      else
        await createEditorialSourceProfile(
          { ...value, operation_id: id },
          { headers },
        );
      await reload();
      setEditing(false);
      if (mounted.current)
        toast.success("来源配置已保存。运行状态以许可、预算和采集回执为准。");
    }, id);
  }
  function poll() {
    if (!selected) return;
    const value = {
      expected_revision: selected.revision,
      reason: reviewReason,
    };
    const id = operation({ poll: selected.id, ...value });
    void perform(async () => {
      setJob(
        await pollEditorialSource(
          { profile_id: selected.id },
          { ...value, operation_id: id },
          { headers },
        ),
      );
      if (mounted.current) toast.success("采集任务已受理，请查看任务回执。");
    }, id);
  }
  function review(
    run: HotKeyAPI.EditorialRunResult,
    action: HotKeyAPI.EditorialRunReviewInput["action"],
  ) {
    if (!selected) return;
    const value = {
      expected_revision: selected.revision,
      reason: reviewReason,
      actor: "operator",
      action,
    };
    const id = operation({ profile: selected.id, run: run.run_id, ...value });
    void perform(async () => {
      await reviewEditorialSourceRun(
        { profile_id: selected.id, run_id: run.run_id },
        { ...value, operation_id: id },
        { headers },
      );
      setRuns(
        await listEditorialSourceRuns(
          { profile_id: selected.id, limit: 100 },
          { headers },
        ),
      );
      await reload();
      if (mounted.current)
        toast.success("人工复核已记录。再次采集需要明确受理新任务。");
    }, id);
  }
  return (
    <>
      <div className="flex flex-col gap-y-8">
        <div>
          <h1 className="text-3xl font-medium">编辑来源配置</h1>
          <p className="text-muted-foreground mt-3">
            六类来源共用批准策略、原内容版本和任务回执。来源健康依据真实完整抓取，默认关闭。
          </p>
        </div>
        <Item variant="muted" asChild>
          <section
            className="flex flex-col gap-y-4 p-5"
            aria-label="操作员权限"
          >
            <ItemContent className="min-w-0 gap-3">
              <Label htmlFor="operator-token">操作员令牌</Label>
              <Input
                id="operator-token"
                type="password"
                autoComplete="off"
                value={token}
                disabled={busy}
                onChange={(e) => {
                  setToken(e.target.value);
                  setPreviewEpoch((value) => value + 1);
                }}
              />
              <ItemDescription className="line-clamp-none">
                令牌仅在当前页面内存中使用。服务端未配置操作员权限时保持关闭。
              </ItemDescription>
              <div className="flex flex-wrap gap-3">
                <Button
                  disabled={!token || busy}
                  onClick={() => void perform(reload)}
                >
                  读取来源
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    setToken("");
                    setProfiles(null);
                    setIcon(null);
                    setIconReason("");
                    setGroups([]);
                    setRuns([]);
                    setJob(null);
                    setSelected(null);
                    setEditing(false);
                  }}
                >
                  清除令牌
                </Button>
                <Button
                  variant="outline"
                  disabled={!token || busy}
                  onClick={() => edit(null)}
                >
                  新增来源
                </Button>
              </div>
            </ItemContent>
          </section>
        </Item>
        {profiles?.length === 0 && (
          <Empty>
            <EmptyHeader>
              <EmptyDescription>
                暂无编辑来源。先创建关闭配置，再批准来源许可与保留策略。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
        {!!profiles?.length && (
          <section
            className="grid gap-4 md:grid-cols-2"
            aria-label="来源与健康"
          >
            {profiles.map((p) => (
              <Item variant="muted" key={p.id} asChild>
                <article className="flex flex-col gap-y-3 p-5">
                  <ItemContent className="min-w-0 gap-3">
                    <ItemTitle className="line-clamp-none w-full">
                      <h2>{p.name}</h2>
                    </ItemTitle>
                    <ItemDescription className="line-clamp-none">
                      {kinds.find(([key]) => key === p.configuration.kind)?.[1]}{" "}
                      ·{p.enabled ? "配置已启用" : "配置关闭"} ·{" "}
                      {p.participation_mode} · {p.tier}
                    </ItemDescription>
                    <p className="text-sm">
                      健康：{p.health} · 连续失败 {p.failure_count} ·{" "}
                      {p.has_unknown_run
                        ? "存在未知请求，需人工复核"
                        : p.has_backlog
                          ? "存在扫描积压"
                          : "无已记录积压"}
                    </p>
                    <dl className="text-muted-foreground flex flex-col gap-y-1 text-sm">
                      <div>最近完整抓取：{time(p.last_ok_at)}</div>
                      <div>最近尝试：{time(p.last_fetch_at)}</div>
                      <div>下次计划：{time(p.next_fetch_at)}</div>
                      <div className="break-all">来源标识：{p.source_key}</div>
                      <div>
                        修订 {p.revision} · 配置版本 {p.configuration_version} ·
                        许可版本 {p.policy_version}
                      </div>
                    </dl>
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => edit(p)}
                    >
                      管理 {p.name}
                    </Button>
                  </ItemContent>
                </article>
              </Item>
            ))}
          </section>
        )}
        {!!groups.length && (
          <section
            className="flex flex-col gap-y-5"
            aria-label="X 分组分页恢复"
          >
            <h2 className="text-xl font-medium">X 分组分页恢复</h2>
            <p className="text-muted-foreground text-sm">
              续页保留原查询和全部成员。配置变化后，需要人工按全部成员版本退回原水位；未知请求先在来源运行记录中核验。
              每个成员须批准 provider_usd_micros
              的来源预算，全局费用与网络计数各记一次。
            </p>
            <Label htmlFor="group-backlog-reason">分组重建原因</Label>
            <Textarea
              id="group-backlog-reason"
              value={groupReason}
              maxLength={1000}
              onChange={(event) => setGroupReason(event.target.value)}
            />
            {groups.map((group) => (
              <Item variant="muted" key={group.group_sha256} asChild>
                <article className="flex flex-col gap-y-3 p-4">
                  <ItemContent className="min-w-0 gap-3">
                    <p className="break-all">{group.query}</p>
                    <p className="text-sm">积压状态：{group.state}</p>
                    <ItemGroup className="flex flex-col gap-y-1 text-sm">
                      {group.members.map((member) => (
                        <Item
                          role="listitem"
                          variant="default"
                          key={member.profile_id}
                        >
                          <ItemContent className="min-w-0 gap-3">
                            {member.name} · 修订 {member.revision} · 配置{" "}
                            {member.configuration_version}
                          </ItemContent>
                        </Item>
                      ))}
                    </ItemGroup>
                    <Button
                      variant="outline"
                      disabled={busy || !token || !groupReason.trim()}
                      onClick={() => restartGroup(group)}
                    >
                      复核全部成员并退回原水位
                    </Button>
                  </ItemContent>
                </article>
              </Item>
            ))}
          </section>
        )}
        {editing && (
          <section className="flex flex-col gap-y-5" aria-label="来源表单">
            <h2 className="text-xl font-medium">
              {selected ? "修改来源" : "新增关闭来源"}
            </h2>
            {formProfileId && (
              <p className="text-muted-foreground text-sm">
                本表单预期修订 {formRevision}。版本变化后请重新打开来源配置。
              </p>
            )}
            <div className="grid gap-5 sm:grid-cols-2">
              <Field className="flex flex-col gap-y-2">
                <FieldLabel htmlFor="source-name">来源名称</FieldLabel>
                <Input
                  id="source-name"
                  value={name}
                  maxLength={128}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
              <Field
                className="flex flex-col gap-y-2"
                data-disabled={!!selected}
              >
                <FieldLabel htmlFor="source-kind">来源类型</FieldLabel>
                <Select
                  value={kind}
                  disabled={!!selected}
                  onValueChange={(selectedValue) => {
                    const next = selectedValue as HotKeyAPI.EditorialSourceKind;
                    setKind(next);
                    setConfig(JSON.stringify(templates[next], null, 2));
                  }}
                >
                  <SelectTrigger id="source-kind" className="w-full min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">来源类型</SelectLabel>
                      {kinds.map(([key, label]) => (
                        <SelectItem
                          key={key}
                          value={key}
                          className="whitespace-normal"
                        >
                          {label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field className="flex flex-col gap-y-2">
                <FieldLabel htmlFor="source-mode">参与模式</FieldLabel>
                <Select
                  value={mode}
                  onValueChange={(selectedValue) =>
                    setMode(selectedValue as HotKeyAPI.ParticipationMode)
                  }
                >
                  <SelectTrigger id="source-mode" className="w-full min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">参与模式</SelectLabel>
                      <SelectItem
                        value="editorial"
                        className="whitespace-normal"
                      >
                        编辑分析
                      </SelectItem>
                      <SelectItem
                        value="hot_signal"
                        className="whitespace-normal"
                      >
                        仅热度信号
                      </SelectItem>
                      <SelectItem
                        value="isolated"
                        className="whitespace-normal"
                      >
                        隔离材料
                      </SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field className="flex flex-col gap-y-2">
                <FieldLabel htmlFor="source-tier">来源分级</FieldLabel>
                <Select
                  value={tier}
                  onValueChange={(selectedValue) =>
                    setTier(selectedValue as typeof tier)
                  }
                >
                  <SelectTrigger id="source-tier" className="w-full min-w-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">来源分级</SelectLabel>
                      {["T1", "T1_5", "T2", "T3"].map((t) => (
                        <SelectItem
                          key={t}
                          value={t}
                          className="whitespace-normal"
                        >
                          {t}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field className="flex flex-col gap-y-2">
                <FieldLabel htmlFor="source-policy">已批准许可版本</FieldLabel>
                <Input
                  id="source-policy"
                  type="number"
                  min={1}
                  value={policy}
                  onChange={(e) => setPolicy(Number(e.target.value))}
                />
              </Field>
              <Field className="flex flex-col gap-y-2">
                <FieldLabel htmlFor="source-interval">
                  采集间隔（分钟）
                </FieldLabel>
                <Input
                  id="source-interval"
                  type="number"
                  min={1}
                  max={360}
                  value={interval}
                  onChange={(e) => setInterval(Number(e.target.value))}
                />
              </Field>
              <Field className="flex flex-col gap-y-2">
                <FieldLabel htmlFor="source-connection">批准连接 ID</FieldLabel>
                <Input
                  id="source-connection"
                  value={connection}
                  onChange={(e) => setConnection(e.target.value)}
                />
                <p className="text-muted-foreground text-sm">
                  X 与公众号必须绑定当前批准连接；密钥在服务端保存。
                </p>
              </Field>
              <Field className="flex flex-col gap-y-2">
                <FieldLabel htmlFor="source-connection-version">
                  批准连接版本
                </FieldLabel>
                <Input
                  id="source-connection-version"
                  type="number"
                  min={1}
                  value={connectionVersion}
                  onChange={(e) => setConnectionVersion(Number(e.target.value))}
                />
              </Field>
            </div>
            <Field orientation="horizontal" className="w-auto">
              <Checkbox
                checked={firstParty}
                onCheckedChange={(checked) => setFirstParty(checked === true)}
                id={`${fieldId}-editorial-source-manager-field-1`}
              />
              <FieldLabel
                htmlFor={`${fieldId}-editorial-source-manager-field-1`}
              >
                第一方来源
              </FieldLabel>
            </Field>
            {selected && (
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  checked={enabled}
                  onCheckedChange={(checked) => setEnabled(checked === true)}
                  id={`${fieldId}-editorial-source-manager-field-2`}
                />
                <FieldLabel
                  htmlFor={`${fieldId}-editorial-source-manager-field-2`}
                >
                  启用来源（仍需批准、凭据与预算）
                </FieldLabel>
              </Field>
            )}
            <Field className="flex flex-col gap-y-2">
              <FieldLabel htmlFor="source-config">配置 JSON</FieldLabel>
              <Textarea
                id="source-config"
                className="min-h-64 font-mono text-sm"
                maxLength={65536}
                value={config}
                onChange={(e) => setConfig(e.target.value)}
              />
              <p className="text-muted-foreground text-sm">
                可设置选择器、分页、时间解释、噪声过滤与官方搜索参数；配置不接受密钥或许可声明。
              </p>
            </Field>
            <Field className="flex flex-col gap-y-2">
              <FieldLabel htmlFor="source-reason">操作原因</FieldLabel>
              <Textarea
                id="source-reason"
                value={reason}
                maxLength={1000}
                onChange={(e) => setReason(e.target.value)}
              />
            </Field>
            <Button
              disabled={busy || !token || !name.trim() || !reason.trim()}
              onClick={save}
            >
              {selected ? "保存来源修订" : "创建关闭来源"}
            </Button>
            <EditorialSourcePreview
              key={`${formProfileId}:${formRevision}:${kind}:${config}:${previewEpoch}`}
              token={token}
              configurationJson={config}
              kind={kind}
              profileId={formProfileId}
              expectedRevision={formRevision}
              sourceEnabled={selected?.enabled ?? false}
            />
          </section>
        )}
        {selected && (
          <EditorialSourceMaterials
            key={`${selected.id}:${selected.source_key}:${previewEpoch}`}
            token={token}
            sourceKey={selected.source_key}
            name={selected.name}
          />
        )}
        {selected && (
          <EditorialLocalApproval
            key={`${selected.id}:${selected.revision}:${selected.configuration_version}`}
            profile={selected}
            token={token}
          />
        )}
        {selected && (
          <section className="flex flex-col gap-y-4" aria-label="来源图标缓存">
            <h2 className="text-xl font-medium">来源图标</h2>
            <p className="text-muted-foreground text-sm">
              仅读现有缓存，正文许可不会授权图标。预期来源修订 {formRevision}
              ；未知请求必须人工核验后受理新任务。
            </p>
            <p>缓存状态：{icon?.status ?? "未读取"}</p>
            {icon?.failure_code && (
              <p className="text-muted-foreground text-sm">
                {icon.failure_code}
              </p>
            )}
            {icon?.next_retry_at && (
              <p className="text-muted-foreground text-sm">
                下次缺项检查：{time(icon.next_retry_at)}
              </p>
            )}
            <Button
              variant="outline"
              disabled={busy || !token}
              onClick={() =>
                void perform(async () =>
                  setIcon(
                    await getEditorialSourceIcon(
                      { profile_id: selected.id },
                      { headers },
                    ),
                  ),
                )
              }
            >
              读取图标状态
            </Button>
            <Label htmlFor="source-icon-reason">图标采集或人工核验原因</Label>
            <Textarea
              id="source-icon-reason"
              value={iconReason}
              maxLength={1000}
              onChange={(event) => setIconReason(event.target.value)}
            />
            <Button
              disabled={
                busy ||
                !token ||
                !selected.enabled ||
                icon?.status === "running" ||
                !iconReason.trim()
              }
              onClick={refreshIcon}
            >
              {icon?.status === "unknown"
                ? "已核验未知请求，重新受理图标"
                : "受理图标采集"}
            </Button>
          </section>
        )}
        {selected && (
          <section
            className="flex flex-col gap-y-5"
            aria-label="来源运行与恢复"
          >
            <h2 className="text-xl font-medium">
              {selected.name} · 运行与恢复
            </h2>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                void perform(async () =>
                  setRuns(
                    await listEditorialSourceRuns(
                      { profile_id: selected.id, limit: 100 },
                      { headers },
                    ),
                  ),
                )
              }
            >
              读取运行记录
            </Button>
            <Field className="flex flex-col gap-y-2">
              <FieldLabel htmlFor="review-reason">采集或复核原因</FieldLabel>
              <Textarea
                id="review-reason"
                value={reviewReason}
                maxLength={1000}
                onChange={(e) => setReviewReason(e.target.value)}
              />
            </Field>
            {selected.configuration.kind !== "external" && (
              <Button
                disabled={
                  busy ||
                  !selected.enabled ||
                  !!selected.has_unknown_run ||
                  !reviewReason.trim()
                }
                onClick={poll}
              >
                受理一次采集
              </Button>
            )}
            {runs.map((run) => (
              <Item variant="muted" key={run.run_id} asChild>
                <article className="flex flex-col gap-y-3 p-4">
                  <ItemContent className="min-w-0 gap-3">
                    <p className="break-all">
                      {run.status} · {run.reason ?? "无附加原因"} · 运行{" "}
                      {run.run_id}
                    </p>
                    <ItemDescription className="line-clamp-none">
                      发现 {run.found ?? 0}，新增 {run.created ?? 0}，修订{" "}
                      {run.revised ?? 0}
                    </ItemDescription>
                    {run.status === "unknown" && (
                      <Button
                        variant="outline"
                        disabled={busy || !reviewReason.trim()}
                        onClick={() => review(run, "acknowledge_unknown")}
                      >
                        核验未知请求
                      </Button>
                    )}
                    {["failed", "blocked"].includes(run.status) && (
                      <Button
                        variant="outline"
                        disabled={busy || !reviewReason.trim()}
                        onClick={() => review(run, "retry_failed")}
                      >
                        允许再次采集
                      </Button>
                    )}
                  </ItemContent>
                </article>
              </Item>
            ))}
            {selected.configuration.kind === "external" && (
              <EditorialExternalIngress
                key={`${selected.id}:${selected.revision}:${selected.configuration_version}:${previewEpoch}`}
                profileId={selected.id}
                expectedRevision={selected.revision}
                configurationVersion={selected.configuration_version}
                enabled={selected.enabled}
              />
            )}
          </section>
        )}
        {job && (
          <Alert role="status">
            <AlertDescription>
              任务已受理：
              <Link
                className="underline underline-offset-4"
                href={`/jobs/${job.id}`}
              >
                查看任务 {job.id}
              </Link>
            </AlertDescription>
          </Alert>
        )}
      </div>
    </>
  );
}
