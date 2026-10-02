"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  getOperatorRelationBench,
  importOperatorRelationBench,
  listOperatorSelectBench,
  runOperatorRelationBench,
} from "@/api/yunyingweihu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/request";

const relations: Record<HotKeyAPI.VerdictRelation, string> = {
  SAME_OCCURRENCE: "同一事实",
  SAME_STORY: "同一故事的新进展",
  UNRELATED: "无关",
  ROUNDUP: "综述提及",
};
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("关系样本必须是 JSON 对象。");
  return value as Record<string, unknown>;
}
function relation(value: unknown): value is HotKeyAPI.VerdictRelation {
  return typeof value === "string" && Object.hasOwn(relations, value);
}
function report(value: unknown): HotKeyAPI.RelationReportInput {
  const row = record(value);
  if (
    typeof row.title !== "string" ||
    !row.title.trim() ||
    row.title.length > 500 ||
    typeof row.source !== "string" ||
    !row.source.trim() ||
    row.source.length > 200
  )
    throw new Error("报道对需要真实标题和来源。");
  return row as HotKeyAPI.RelationReportInput;
}
export function normalizeRelationGold(
  input: string,
): HotKeyAPI.RelationGoldCaseInput[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(input);
  } catch {
    parsed = input
      .trim()
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  }
  const rows = Array.isArray(parsed)
    ? parsed
    : typeof record(parsed).case_id === "string"
      ? [parsed]
      : record(parsed).cases;
  if (!Array.isArray(rows) || !rows.length || rows.length > 5000)
    throw new Error("需要 1 到 5000 条固定报道对。");
  const ids = new Set<string>();
  return rows.map((value) => {
    const row = record(value);
    if (
      typeof row.case_id !== "string" ||
      !row.case_id.trim() ||
      row.case_id.length > 200 ||
      ids.has(row.case_id) ||
      !relation(row.gold_relation)
    )
      throw new Error("样本编号必须唯一,关系只能使用四种正式分类。");
    ids.add(row.case_id);
    return {
      ...row,
      case_id: row.case_id,
      gold_relation: row.gold_relation,
      a: report(row.a),
      b: report(row.b),
    } as HotKeyAPI.RelationGoldCaseInput;
  });
}
export function normalizeRelationPredictions(
  input: unknown,
): Record<string, HotKeyAPI.RelationPredictionInput[]> {
  return Object.fromEntries(
    Object.entries(record(input)).map(([model, raw]) => {
      if (
        !model.trim() ||
        !Array.isArray(raw) ||
        !raw.length ||
        raw.length > 5000
      )
        throw new Error("导入结果需要每个模型的逐条预测。");
      const rows = raw.map((value) => {
        const row = record(value);
        if (typeof row.case_id !== "string" || !row.case_id.trim())
          throw new Error("预测结果缺少样本编号。");
        if (row.relation == null) {
          if (
            typeof row.error_code !== "string" ||
            !row.error_code ||
            row.confidence != null
          )
            throw new Error("失败结果需要错误代码,不得伪造关系或置信度。");
        } else if (
          !relation(row.relation) ||
          typeof row.confidence !== "number" ||
          !Number.isFinite(row.confidence) ||
          row.confidence < 0 ||
          row.confidence > 1 ||
          row.error_code != null
        ) {
          throw new Error("有效预测需要四类关系和 0 到 1 的置信度。");
        }
        return row as HotKeyAPI.RelationPredictionInput;
      });
      return [model, rows];
    }),
  );
}

export function RelationBench({ token }: { token: string }) {
  const [runs, setRuns] = useState<HotKeyAPI.SelectBenchRunView[]>([]);
  const [mode, setMode] = useState<"run" | "import">("run");
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [reason, setReason] = useState("");
  const [models, setModels] = useState("");
  const [split, setSplit] = useState("");
  const [seed, setSeed] = useState("42");
  const [sample, setSample] = useState("100");
  const [selected, setSelected] = useState("");
  const [page, setPage] = useState<HotKeyAPI.RelationBenchCasesView | null>(
    null,
  );
  const [disagree, setDisagree] = useState(false);
  const [errors, setErrors] = useState(false);
  const [jobs, setJobs] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const operation = useRef<{ payload: string; id: string } | null>(null);
  const options = { headers: { "X-HotKey-Operator-Token": token } };
  useEffect(() => {
    let active = true;
    listOperatorSelectBench({ headers: { "X-HotKey-Operator-Token": token } })
      .then((rows) => {
        if (active) setRuns(rows.filter((row) => row.kind === "relation"));
      })
      .catch(() => {
        if (active) setMessage("关系评测目录读取失败,可以按编号读取。");
      });
    return () => {
      active = false;
    };
  }, [token]);
  function fail(error: unknown) {
    setMessage(
      error instanceof ApiRequestError
        ? `${error.message}。输入已保留。`
        : error instanceof SyntaxError
          ? "JSON 格式无效,输入已保留。"
          : `${error instanceof Error ? error.message : "评测操作失败"}。输入已保留。`,
    );
  }
  async function load(runId = selected, cursor?: string) {
    if (!runId) return;
    setBusy(true);
    try {
      const result = await getOperatorRelationBench(
        { run_id: runId, cursor, limit: 50, disagree, errors },
        options,
      );
      setPage((old) =>
        cursor && old && old.run.id === result.run.id
          ? { ...result, items: [...old.items, ...result.items] }
          : result,
      );
      setSelected(runId);
      setMessage("");
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("文件不得超过 20 MiB");
      const text = await file.text();
      const cases = normalizeRelationGold(text);
      const predictions =
        mode === "import"
          ? normalizeRelationPredictions(record(JSON.parse(text)).predictions)
          : null;
      const names = predictions
        ? Object.keys(predictions)
        : models
            .split(/[,，\n]/)
            .map((s) => s.trim())
            .filter(Boolean);
      const base = {
        label,
        reason,
        models: names,
        cases,
        sample_size: Number(sample),
        seed: Number(seed),
        split: split || null,
      };
      const payload = JSON.stringify({ mode, ...base, predictions });
      if (operation.current?.payload !== payload)
        operation.current = { payload, id: crypto.randomUUID() };
      let run: HotKeyAPI.SelectBenchRunView;
      if (predictions) {
        run = await importOperatorRelationBench(
          { ...base, predictions, operation_id: operation.current.id },
          options,
        );
        setJobs([]);
      } else {
        const accepted = await runOperatorRelationBench(
          { ...base, operation_id: operation.current.id },
          options,
        );
        run = accepted.run;
        setJobs(accepted.job_ids);
      }
      operation.current = null;
      setRuns((old) => [run, ...old.filter((item) => item.id !== run.id)]);
      setSelected(run.id);
      setPage(null);
      setMessage(
        predictions
          ? "结果已导入,服务端按逐条预测复算指标。"
          : "固定报道对已排队。未知响应保留待核查,不会自动重新付费。",
      );
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="grid gap-5">
      <h2 className="text-xl font-semibold">关系评测</h2>
      <p className="text-muted-foreground text-sm">
        固定报道对区分同一事实、后续进展、无关与综述。失败结果单独保留；导入只复算指标。排队使用生产提示词和当前预算,供应商开关默认关闭。
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1">
          方式
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "run" | "import")}
            className="bg-muted rounded-md p-2"
          >
            <option value="run">排队固定报道对</option>
            <option value="import">导入逐条预测</option>
          </select>
        </label>
        <label className="grid gap-1">
          关系评测名称
          <Input
            required
            aria-label="关系评测名称"
            maxLength={200}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <label className="grid gap-1 sm:col-span-2">
          关系评测原因
          <Input
            required
            aria-label="关系评测原因"
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        {mode === "run" ? (
          <label className="grid gap-1 sm:col-span-2">
            关系评测模型
            <Input
              required
              aria-label="关系评测模型"
              value={models}
              placeholder="当前已配置模型,逗号分隔,最多 5 个"
              onChange={(e) => setModels(e.target.value)}
            />
          </label>
        ) : null}
        <label className="grid gap-1">
          分组
          <Input
            maxLength={64}
            value={split}
            onChange={(e) => setSplit(e.target.value)}
          />
        </label>
        <label className="grid gap-1">
          随机种子
          <Input
            required
            type="number"
            step={1}
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
        </label>
        <label className="grid gap-1">
          排队样本量
          <Input
            required
            type="number"
            min={1}
            max={100}
            value={sample}
            onChange={(e) => setSample(e.target.value)}
          />
        </label>
        <label className="grid min-w-0 gap-1 sm:col-span-2">
          关系样本 JSON / JSONL（最多 20 MiB）
          <Input
            required
            type="file"
            accept=".json,.jsonl,application/json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <p className="text-muted-foreground text-xs sm:col-span-2">
          样本格式: cases 中每条含 case_id、a / b（title、source、可选 summary /
          frame）和 gold_relation。导入还需要 predictions: 模型名→逐条
          case_id、relation、confidence；失败项用 relation: null 和 error_code。
        </p>
        <Button type="submit" disabled={busy} className="justify-self-start">
          {mode === "run" ? "排队关系评测" : "导入并复算关系评测"}
        </Button>
      </form>
      {jobs.length ? (
        <div className="flex flex-wrap gap-3">
          {jobs.map((id) => (
            <Link key={id} href={`/jobs/${id}`} className="text-sm underline">
              任务 {id.slice(0, 8)}
            </Link>
          ))}
        </div>
      ) : null}
      <form
        className="flex flex-wrap gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
      >
        <Input
          aria-label="关系评测运行编号"
          placeholder="运行编号,可读取历史评测"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="min-w-48 flex-1"
        />
        <Button disabled={busy || !selected} type="submit" variant="secondary">
          读取 / 刷新关系评测
        </Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {runs.map((run) => (
          <Button
            key={run.id}
            disabled={busy}
            variant={selected === run.id ? "secondary" : "ghost"}
            onClick={() => void load(run.id)}
          >
            {run.label} · {run.sample_size} 对
          </Button>
        ))}
      </div>
      {page ? (
        <>
          <p className="text-muted-foreground text-xs break-all">
            黄金集 {page.run.gold_fingerprint} · {page.run.prompt_version} ·{" "}
            {page.run.split ?? "无分组"} · seed {page.run.seed ?? "未知"}
          </p>
          <details>
            <summary className="cursor-pointer">
              指标、混淆矩阵与错误覆盖
            </summary>
            <pre className="bg-muted/40 mt-3 max-h-96 overflow-auto rounded-lg p-4 text-xs">
              {JSON.stringify(page.run.summary, null, 2)}
            </pre>
          </details>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void load();
            }}
            className="flex flex-wrap items-center gap-4"
          >
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={disagree}
                onChange={(e) => setDisagree(e.target.checked)}
              />
              仅模型分歧
            </label>
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={errors}
                onChange={(e) => setErrors(e.target.checked)}
              />
              仅错误 / 未知
            </label>
            <Button disabled={busy} variant="outline" type="submit">
              应用关系筛选
            </Button>
          </form>
          <div className="grid gap-4">
            {page.items.map((row) => (
              <article
                key={row.case.case_id}
                className="bg-muted/40 min-w-0 rounded-lg p-4"
              >
                <h3 className="font-medium">
                  {row.case.case_id} · gold {relations[row.case.gold_relation]}
                </h3>
                <p className="text-muted-foreground text-xs">
                  {row.case.stratum ?? "未分层"} · {row.case.split ?? "无分组"}
                </p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {(["a", "b"] as const).map((key) => (
                    <div key={key}>
                      <p>
                        {key.toUpperCase()} · {row.case[key].source}{" "}
                        {row.case[key].first_party ? "· 第一方" : ""}
                      </p>
                      <p className="font-medium">{row.case[key].title}</p>
                      <p className="text-muted-foreground text-sm">
                        {row.case[key].summary}
                      </p>
                      {row.case[key].frame ? (
                        <pre className="mt-2 overflow-auto text-xs">
                          {JSON.stringify(row.case[key].frame, null, 2)}
                        </pre>
                      ) : null}
                    </div>
                  ))}
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {Object.entries(row.by_model).map(([model, value]) => {
                    const prediction =
                      value as HotKeyAPI.RelationPredictionInput;
                    return (
                      <div key={model} className="min-w-0">
                        <p className="break-all">
                          {model} ·{" "}
                          {prediction.relation
                            ? relations[prediction.relation]
                            : "错误 / 未知"}
                          {prediction.confidence == null
                            ? ""
                            : ` · ${(prediction.confidence * 100).toFixed(1)}%`}
                        </p>
                        <p className="text-muted-foreground text-sm">
                          {prediction.error_code ??
                            prediction.difference ??
                            "未提供差异说明"}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
          {page.next_cursor ? (
            <Button
              disabled={busy}
              variant="ghost"
              className="justify-self-start"
              onClick={() => void load(page.run.id, page.next_cursor!)}
            >
              加载更多关系样本
            </Button>
          ) : null}
        </>
      ) : null}
      {message ? (
        <p role="status" className="text-sm">
          {message}
        </p>
      ) : null}
    </section>
  );
}
