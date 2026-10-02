"use client";
import { useEffect, useState } from "react";
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
      <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
        <label className="grid gap-2">
          来源键
          <Input
            required
            maxLength={64}
            value={draft.source_key}
            disabled={draft.expected_revision != null}
            onChange={(e) => setDraft({ ...draft, source_key: e.target.value })}
          />
        </label>
        <label className="grid gap-2">
          来源名称
          <Input
            required
            maxLength={200}
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </label>
        <label className="grid gap-2">
          范围类型
          <select
            className="bg-muted rounded-md p-2"
            value={draft.selector_kind}
            disabled={draft.expected_revision != null}
            onChange={(e) =>
              setDraft({
                ...draft,
                selector_kind: e.target
                  .value as HotKeyAPI.AttentionSourceInput["selector_kind"],
              })
            }
          >
            {["native_scope", "source", "author", "canonical_host"].map(
              (value) => (
                <option key={value}>{value}</option>
              ),
            )}
          </select>
        </label>
        <label className="grid gap-2">
          范围标识
          <Input
            required
            maxLength={512}
            disabled={draft.expected_revision != null}
            value={draft.selector_ref}
            onChange={(e) =>
              setDraft({ ...draft, selector_ref: e.target.value })
            }
            placeholder="hotlist:weibo 或 search:请求哈希"
          />
        </label>
        <label className="grid gap-2">
          角色
          <select
            className="bg-muted rounded-md p-2"
            value={draft.mode}
            onChange={(e) =>
              setDraft({
                ...draft,
                mode: e.target.value as HotKeyAPI.AttentionSourceInput["mode"],
              })
            }
          >
            <option value="editorial">编辑报道</option>
            <option value="signal">传播信号</option>
            <option value="isolated">隔离</option>
          </select>
        </label>
        <label className="grid gap-2">
          质量层级
          <select
            className="bg-muted rounded-md p-2"
            value={draft.tier ?? ""}
            onChange={(e) =>
              setDraft({
                ...draft,
                tier: (e.target.value ||
                  null) as HotKeyAPI.AttentionSourceInput["tier"],
              })
            }
          >
            <option value="">未分级</option>
            {["T1", "T1_5", "T2"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="grid gap-2">
          集团键
          <Input
            maxLength={128}
            value={draft.group_key ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, group_key: e.target.value || null })
            }
          />
        </label>
        <label className="grid gap-2">
          实体键
          <Input
            maxLength={128}
            value={draft.owner_entity_key ?? ""}
            onChange={(e) =>
              setDraft({ ...draft, owner_entity_key: e.target.value || null })
            }
          />
        </label>
        <label className="grid gap-2">
          计划间隔（秒）
          <Input
            type="number"
            min={60}
            max={604800}
            value={draft.interval_seconds}
            onChange={(e) =>
              setDraft({ ...draft, interval_seconds: Number(e.target.value) })
            }
          />
        </label>
        <div className="flex flex-wrap items-center gap-4">
          {(["enabled", "scheduled", "first_party"] as const).map(
            (key, index) => (
              <label key={key} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={draft[key] ?? false}
                  onChange={(e) =>
                    setDraft({ ...draft, [key]: e.target.checked })
                  }
                />
                {["启用", "计划采集", "第一方"][index]}
              </label>
            ),
          )}
        </div>
        <div className="flex gap-2">
          <Button disabled={busy} type="submit">
            保存来源身份
          </Button>
          <Button type="button" variant="ghost" onClick={() => setDraft(blank)}>
            新建来源身份
          </Button>
        </div>
      </form>
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}
