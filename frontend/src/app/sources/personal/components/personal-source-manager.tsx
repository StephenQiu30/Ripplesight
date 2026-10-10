"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  listPersonalSources,
  createPersonalSource,
  updatePersonalSource,
} from "@/api/gerenlaiyuan";
import { PageHeader } from "@/components/system/page-header";
import { PageState } from "@/components/system/page-state";
import * as UI from "@/components/ui/content";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

type Profile = HotKeyAPI.EditorialProfileView;
type Kind = "rss" | "web_list" | "json_list";
const kinds: Record<Kind, string> = {
  rss: "RSS / Atom",
  web_list: "网页列表",
  json_list: "JSON 列表",
};

function initialConfig(kind: Kind) {
  return JSON.stringify(
    kind === "web_list"
      ? {
          kind,
          url: "",
          allowed_hosts: [],
          item_selector: "article",
          link_selector: "a",
          title_selector: "h2",
        }
      : {
          kind,
          url: "",
          allowed_hosts: [],
          items_path: "items",
          title_paths: ["title"],
          url_template: "{raw:url}",
        },
    null,
    2,
  );
}

function failureMessage(cause: unknown) {
  if (!(cause instanceof ApiRequestError)) return "来源暂时无法保存，请重试。";
  if (cause.code === "editorial_version_conflict")
    return "来源已更新，请重新读取并打开表单。当前输入已保留。";
  if (
    [
      "source_policy_unavailable",
      "source_access_unavailable",
      "retention_policy_unavailable",
      "editorial_source_unavailable",
    ].includes(cause.code ?? "")
  )
    return "来源许可或保留策略尚未满足，请先保持停用并联系站点维护者。";
  if (cause.status === 401 || cause.status === 403)
    return "当前账户无权操作此来源，请重新登录后重试。";
  return "来源未能保存，请检查地址、解析配置和来源许可后重试。";
}

export function PersonalSourceManager() {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("rss");
  const [url, setUrl] = useState("");
  const [config, setConfig] = useState("");
  const [interval, setInterval] = useState("30");
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const operations = useRef(new Map<string, string>());

  const load = useCallback(() => {
    const current = ++generation.current;
    return listPersonalSources()
      .then((values) => {
        if (mounted.current && current === generation.current) {
          setProfiles(values);
          setLoadError(null);
        }
      })
      .catch((cause: unknown) => {
        if (mounted.current && current === generation.current)
          setLoadError(cause);
      });
  }, []);
  useEffect(() => {
    mounted.current = true;
    const pending = generation;
    void load();
    return () => {
      mounted.current = false;
      ++pending.current;
    };
  }, [load]);

  function edit(value: Profile | null) {
    setProfile(value);
    setName(value?.name ?? "");
    setKind((value?.configuration.kind as Kind) ?? "rss");
    setUrl(value?.configuration.feed_url ?? "");
    setConfig(value ? JSON.stringify(value.configuration, null, 2) : "");
    setInterval(String(value?.interval_minutes ?? 30));
    setEnabled(value?.enabled ?? false);
    setUnknown(false);
    setSaveError(null);
    setSaved(false);
    setEditing(true);
    operations.current.clear();
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    let configuration: HotKeyAPI.EditorialSourceConfiguration;
    try {
      if (kind === "rss") {
        const address = new URL(url);
        if (
          !["http:", "https:"].includes(address.protocol) ||
          address.username ||
          address.password
        )
          throw new Error();
        configuration = {
          ...profile?.configuration,
          kind,
          feed_url: url,
          allowed_hosts: [address.hostname],
        };
      } else {
        configuration = JSON.parse(
          config,
        ) as HotKeyAPI.EditorialSourceConfiguration;
        if (!configuration || configuration.kind !== kind) throw new Error();
      }
    } catch {
      setSaveError(
        kind === "rss"
          ? "请填写不含账号密码的完整 HTTP 或 HTTPS 订阅地址。"
          : "请填写与来源类型一致的解析配置 JSON。地址和允许域名不能为空。",
      );
      return;
    }
    const body = {
      expected_revision: profile?.revision ?? 0,
      name: name.trim(),
      enabled: profile ? enabled : false,
      configuration,
      policy_version: profile?.policy_version ?? 1,
      interval_minutes: Number(interval),
    };
    const key = JSON.stringify({ id: profile?.id, ...body });
    if (!operations.current.has(key))
      operations.current.set(key, crypto.randomUUID());
    const command = { ...body, operation_id: operations.current.get(key)! };
    setBusy(true);
    setSaveError(null);
    try {
      const value = profile
        ? await updatePersonalSource({ profile_id: profile.id }, command)
        : await createPersonalSource(command);
      if (!mounted.current) return;
      ++generation.current;
      setProfiles((values) =>
        [...(values ?? []).filter((item) => item.id !== value.id), value].sort(
          (a, b) => a.name.localeCompare(b.name),
        ),
      );
      setEditing(false);
      setUnknown(false);
      setSaved(true);
    } catch (cause) {
      if (!mounted.current) return;
      const uncertain =
        cause instanceof ApiRequestError &&
        ["network", "timeout", "protocol", "cancelled"].includes(cause.kind);
      setUnknown(uncertain);
      setSaveError(
        uncertain
          ? "保存结果尚未确认，当前输入已锁定。请重试本次保存以核对原操作，避免重复新增。"
          : failureMessage(cause),
      );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  const locked = busy || unknown;
  return (
    <UI.Content layout="stack" className="gap-6">
      <PageHeader
        title={<>我的来源</>}
        description={
          <>
            添加自己的 RSS、网页或 JSON 列表来源，仅用于当前账户的监控与阅读。
          </>
        }
        actions={
          <Button disabled={busy || unknown} onClick={() => edit(null)}>
            新增来源
          </Button>
        }
      />
      <UI.Content className="flex flex-wrap gap-3">
        <Button asChild variant="outline">
          <Link href="/sources">平台接入</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/monitors/new">设置关键词并选择来源</Link>
        </Button>
      </UI.Content>
      {saved && <UI.Text role="status">来源配置已保存。</UI.Text>}
      {loadError ? (
        <PageState
          headingLevel={2}
          state={
            loadError instanceof ApiRequestError &&
            [401, 403].includes(loadError.status ?? 0)
              ? "forbidden"
              : "error"
          }
          title="个人来源暂时无法读取"
          description="当前输入会保留，重新读取后可继续管理。"
          action={
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void load()}
            >
              重新读取来源
            </Button>
          }
        />
      ) : profiles === null ? (
        <PageState headingLevel={2} state="loading" title="正在读取个人来源" />
      ) : !profiles.length ? (
        <PageState
          headingLevel={2}
          state="empty"
          title="还没有个人来源"
          description="添加 RSS 订阅地址或网页列表，保存后再选择用于监控的来源。"
        />
      ) : (
        <UI.Content
          as="section"
          aria-label="个人来源列表"
          className="grid gap-4 md:grid-cols-2"
        >
          {profiles.map((item) => (
            <Card key={item.id}>
              <CardHeader>
                <CardTitle>
                  <UI.Heading level={2}>{item.name}</UI.Heading>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <UI.Text size="sm">
                  {kinds[item.configuration.kind as Kind]} ·{" "}
                  {item.enabled ? "已启用" : "已停用"} · 每{" "}
                  {item.interval_minutes} 分钟更新
                </UI.Text>
                <UI.Text size="sm" tone="muted" className="break-all">
                  {item.configuration.feed_url ?? item.configuration.url}
                </UI.Text>
                <Button
                  variant="outline"
                  disabled={busy || unknown}
                  onClick={() => edit(item)}
                >
                  编辑 {item.name}
                </Button>
              </CardContent>
            </Card>
          ))}
        </UI.Content>
      )}
      {editing && (
        <Card>
          <CardHeader>
            <CardTitle>
              <UI.Heading level={2}>
                {profile ? "编辑个人来源" : "新增个人来源"}
              </UI.Heading>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <UI.Form
              onSubmit={(event) => void save(event)}
              className="flex flex-col gap-5"
            >
              <Field>
                <FieldLabel htmlFor="personal-source-name">来源名称</FieldLabel>
                <Input
                  id="personal-source-name"
                  required
                  maxLength={128}
                  value={name}
                  disabled={locked}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="personal-source-kind">来源类型</FieldLabel>
                <Select
                  value={kind}
                  disabled={locked || !!profile}
                  onValueChange={(value) => {
                    setKind(value as Kind);
                    setConfig(initialConfig(value as Kind));
                  }}
                >
                  <SelectTrigger id="personal-source-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {Object.entries(kinds).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              {kind === "rss" ? (
                <Field>
                  <FieldLabel htmlFor="personal-source-url">
                    订阅地址
                  </FieldLabel>
                  <Input
                    id="personal-source-url"
                    type="url"
                    required
                    value={url}
                    disabled={locked}
                    onChange={(event) => setUrl(event.target.value)}
                  />
                </Field>
              ) : (
                <Field>
                  <FieldLabel htmlFor="personal-source-config">
                    解析配置
                  </FieldLabel>
                  <Textarea
                    id="personal-source-config"
                    required
                    rows={12}
                    value={config}
                    disabled={locked}
                    onChange={(event) => setConfig(event.target.value)}
                  />
                  <FieldDescription>
                    填写来源地址、允许域名和列表解析规则。
                  </FieldDescription>
                </Field>
              )}
              <Field>
                <FieldLabel htmlFor="personal-source-interval">
                  更新周期（分钟）
                </FieldLabel>
                <Input
                  id="personal-source-interval"
                  type="number"
                  min={1}
                  max={360}
                  required
                  value={interval}
                  disabled={locked}
                  onChange={(event) => setInterval(event.target.value)}
                />
              </Field>
              {profile && (
                <Field orientation="horizontal">
                  <Switch
                    id="personal-source-enabled"
                    checked={enabled}
                    disabled={locked}
                    onCheckedChange={setEnabled}
                  />
                  <FieldLabel htmlFor="personal-source-enabled">
                    启用来源
                  </FieldLabel>
                </Field>
              )}
              <UI.Text size="sm" tone="muted">
                新来源默认停用。启用前需满足来源许可与采集条件，可用后可在自己的监控主题中选择。
              </UI.Text>
              {saveError && (
                <Alert variant="destructive">
                  <AlertDescription>{saveError}</AlertDescription>
                </Alert>
              )}
              <UI.Content className="flex flex-wrap gap-3">
                <Button type="submit" disabled={busy}>
                  {busy ? "正在保存" : unknown ? "重试本次保存" : "保存来源"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={locked}
                  onClick={() => setEditing(false)}
                >
                  取消
                </Button>
                {profile && !unknown && (
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={busy}
                    onClick={() => void load()}
                  >
                    重新读取最新来源
                  </Button>
                )}
              </UI.Content>
            </UI.Form>
          </CardContent>
        </Card>
      )}
    </UI.Content>
  );
}
