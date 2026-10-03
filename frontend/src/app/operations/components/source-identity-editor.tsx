"use client";
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
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";
import { useId, useEffect, useState } from "react";
import {
  listEventAttentionSources,
  upsertEventAttentionSource,
} from "@/api/shijian";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/request";
const blank: HotKeyAPI.AttentionSourceInput = {
  source_key: "",
  selector_kind: "native_scope",
  selector_ref: "",
  name: "",
  mode: "editorial",
  enabled: true,
  scheduled: true,
  interval_seconds: 1800,
  tier: "T2",
  first_party: false,
};
export function SourceIdentityEditor({ token }: { token: string }) {
  const fieldId = useId();

  const [rows, setRows] = useState<HotKeyAPI.AttentionSourceView[]>([]);
  const [draft, setDraft] = useState(blank);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    listEventAttentionSources()
      .then((v) => {
        if (live) setRows(v);
      })
      .catch(() => {
        if (live) setMessage("来源身份读取失败");
      });
    return () => {
      live = false;
    };
  }, []);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const row = await upsertEventAttentionSource(draft, {
        headers: { "X-HotKey-Operator-Token": token },
      });
      setRows((current) => [
        ...current.filter((item) => item.id !== row.id),
        row,
      ]);
      setDraft(blank);
      setMessage("来源身份已保存。");
    } catch (error) {
      setMessage(
        error instanceof ApiRequestError
          ? error.message
          : "来源身份保存失败，请刷新版本后重试。",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="grid gap-5">
      <h2 className="text-xl font-semibold">来源独立性与热度</h2>
      <p className="text-muted-foreground text-sm">
        集团或同一实体的来源只计算一个独立参与者。搜索、评论、榜单和网页的成功时间按实际请求范围更新。
      </p>
      <div className="grid gap-2">
        {rows.map((row) => (
          <div
            key={row.id}
            className="bg-muted/40 flex flex-wrap items-center justify-between gap-2 rounded-lg p-3"
          >
            <span className="min-w-0 break-all">
              {row.name} · {row.mode} · {row.selector_kind}:{row.selector_ref}
              <span className="text-muted-foreground block text-xs">
                版本 {row.revision} · 成功采集{" "}
                {row.last_successful_fetch_at ?? "尚无成功记录"}
              </span>
            </span>
            <Button
              variant="ghost"
              onClick={() =>
                setDraft({
                  source_key: row.source_key,
                  selector_kind:
                    row.selector_kind as HotKeyAPI.AttentionSourceInput["selector_kind"],
                  selector_ref: row.selector_ref,
                  name: row.name,
                  mode: row.mode,
                  group_key: row.group_key,
                  owner_entity_key: row.owner_entity_key,
                  tier: row.tier,
                  first_party: row.first_party,
                  scheduled: row.scheduled,
                  enabled: row.enabled,
                  interval_seconds: row.interval_seconds,
                  expected_revision: row.revision,
                })
              }
            >
              编辑 {row.name}
            </Button>
          </div>
        ))}
      </div>
      <form onSubmit={save}>
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          <Field
            className="min-w-0"
            data-disabled={draft.expected_revision != null}
          >
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-1`}>
              来源键
            </FieldLabel>
            <Input
              required
              maxLength={64}
              value={draft.source_key}
              disabled={draft.expected_revision != null}
              onChange={(e) =>
                setDraft({ ...draft, source_key: e.target.value })
              }
              id={`${fieldId}-source-identity-editor-field-1`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-2`}>
              来源名称
            </FieldLabel>
            <Input
              required
              maxLength={200}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              id={`${fieldId}-source-identity-editor-field-2`}
            />
          </Field>
          <Field
            className="min-w-0"
            data-disabled={draft.expected_revision != null}
          >
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-3`}>
              范围类型
            </FieldLabel>
            <Select
              value={draft.selector_kind}
              disabled={draft.expected_revision != null}
              onValueChange={(selectedValue) =>
                setDraft({
                  ...draft,
                  selector_kind:
                    selectedValue as HotKeyAPI.AttentionSourceInput["selector_kind"],
                })
              }
            >
              <SelectTrigger
                id={`${fieldId}-source-identity-editor-field-3`}
                className="w-full min-w-0"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectGroup>
                  <SelectLabel className="sr-only">范围类型</SelectLabel>
                  {["native_scope", "source", "author", "canonical_host"].map(
                    (value) => (
                      <SelectItem
                        key={value}
                        value={value}
                        className="whitespace-normal"
                      >
                        {value}
                      </SelectItem>
                    ),
                  )}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          <Field
            className="min-w-0"
            data-disabled={draft.expected_revision != null}
          >
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-4`}>
              范围标识
            </FieldLabel>
            <Input
              required
              maxLength={512}
              disabled={draft.expected_revision != null}
              value={draft.selector_ref}
              onChange={(e) =>
                setDraft({ ...draft, selector_ref: e.target.value })
              }
              placeholder="hotlist:weibo 或 search:请求哈希"
              id={`${fieldId}-source-identity-editor-field-4`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-5`}>
              角色
            </FieldLabel>
            <Select
              value={draft.mode}
              onValueChange={(selectedValue) =>
                setDraft({
                  ...draft,
                  mode: selectedValue as HotKeyAPI.AttentionSourceInput["mode"],
                })
              }
            >
              <SelectTrigger
                id={`${fieldId}-source-identity-editor-field-5`}
                className="w-full min-w-0"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectGroup>
                  <SelectLabel className="sr-only">角色</SelectLabel>
                  <SelectItem value="editorial" className="whitespace-normal">
                    编辑报道
                  </SelectItem>
                  <SelectItem value="signal" className="whitespace-normal">
                    传播信号
                  </SelectItem>
                  <SelectItem value="isolated" className="whitespace-normal">
                    隔离
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-6`}>
              质量层级
            </FieldLabel>
            <Select
              value={draft.tier ?? ""}
              onValueChange={(selectedValue) =>
                setDraft({
                  ...draft,
                  tier: ((selectedValue === "__none__" ? "" : selectedValue) ||
                    null) as HotKeyAPI.AttentionSourceInput["tier"],
                })
              }
            >
              <SelectTrigger
                id={`${fieldId}-source-identity-editor-field-6`}
                className="w-full min-w-0"
              >
                <SelectValue placeholder="未分级" />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectGroup>
                  <SelectLabel className="sr-only">质量层级</SelectLabel>
                  <SelectItem value="__none__" className="whitespace-normal">
                    未分级
                  </SelectItem>
                  {["T1", "T1_5", "T2"].map((value) => (
                    <SelectItem
                      key={value}
                      value={value}
                      className="whitespace-normal"
                    >
                      {value}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-7`}>
              集团键
            </FieldLabel>
            <Input
              maxLength={128}
              value={draft.group_key ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, group_key: e.target.value || null })
              }
              id={`${fieldId}-source-identity-editor-field-7`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-8`}>
              实体键
            </FieldLabel>
            <Input
              maxLength={128}
              value={draft.owner_entity_key ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, owner_entity_key: e.target.value || null })
              }
              id={`${fieldId}-source-identity-editor-field-8`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-source-identity-editor-field-9`}>
              计划间隔（秒）
            </FieldLabel>
            <Input
              type="number"
              min={60}
              max={604800}
              value={draft.interval_seconds}
              onChange={(e) =>
                setDraft({ ...draft, interval_seconds: Number(e.target.value) })
              }
              id={`${fieldId}-source-identity-editor-field-9`}
            />
          </Field>
          <div className="flex flex-wrap items-center gap-4">
            {(["enabled", "scheduled", "first_party"] as const).map(
              (key, index) => (
                <Field key={key} orientation="horizontal" className="w-auto">
                  <Checkbox
                    checked={draft[key] ?? false}
                    onCheckedChange={(checked) =>
                      setDraft({ ...draft, [key]: checked === true })
                    }
                    id={`${fieldId}-source-identity-editor-field-10-${key}`}
                  />
                  <FieldLabel
                    htmlFor={`${fieldId}-source-identity-editor-field-10-${key}`}
                  >
                    {["启用", "计划采集", "第一方"][index]}
                  </FieldLabel>
                </Field>
              ),
            )}
          </div>
          <div className="flex gap-2">
            <Button disabled={busy} type="submit">
              保存来源身份
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDraft(blank)}
            >
              新建来源身份
            </Button>
          </div>
        </FieldGroup>
      </form>
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}
