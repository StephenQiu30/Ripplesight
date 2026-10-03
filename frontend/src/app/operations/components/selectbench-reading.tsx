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
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";
import { useId, useEffect, useRef, useState } from "react";
import {
  listOperatorSelectBench,
  getOperatorSelectBench,
  importOperatorSelectBench,
} from "@/api/yunyingweihu";
import { SelectBenchRunner } from "./selectbench-runner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/request";

export function SelectBenchReading({ token }: { token: string }) {
  const fieldId = useId();

  const [runs, setRuns] = useState<HotKeyAPI.SelectBenchRunView[]>([]);
  const [selected, setSelected] = useState("");
  const [cases, setCases] = useState<HotKeyAPI.SelectBenchCasesView | null>(
    null,
  );
  const [model, setModel] = useState("");
  const [outcome, setOutcome] = useState("");
  const [stratum, setStratum] = useState("");
  const [disagree, setDisagree] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const identity = useRef<{ payload: string; id: string } | null>(null);
  useEffect(() => {
    let live = true;
    listOperatorSelectBench({ headers: { "X-HotKey-Operator-Token": token } })
      .then((rows) => {
        if (live) setRuns(rows);
      })
      .catch(() => {
        if (live) setMessage("评测读取失败");
      });
    return () => {
      live = false;
    };
  }, [token]);
  const options = { headers: { "X-HotKey-Operator-Token": token } };
  function fail(error: unknown) {
    setMessage(
      error instanceof ApiRequestError
        ? error.message
        : error instanceof SyntaxError
          ? "文件包含无效 JSON。"
          : "评测操作失败，请保留输入后重试。",
    );
  }
  async function load(runId = selected, cursor?: string) {
    if (!runId) return;
    setBusy(true);
    try {
      const page = await getOperatorSelectBench(
        {
          run_id: runId,
          model: model || undefined,
          outcome: (outcome ||
            undefined) as HotKeyAPI.getOperatorSelectBenchParams["outcome"],
          stratum: stratum || undefined,
          disagree,
          cursor,
          limit: 50,
        },
        options,
      );
      setCases((old) =>
        cursor && old
          ? { ...page, items: [...old.items, ...page.items] }
          : page,
      );
      setSelected(runId);
      setMessage("");
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }
  async function importReport(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("file too large");
      const parsed: Record<string, unknown> = JSON.parse(await file.text());
      const models =
        parsed.models ??
        Object.fromEntries(
          Object.entries(parsed).filter(([key]) => key !== "meta"),
        );
      if (!models || typeof models !== "object" || Array.isArray(models))
        throw new Error("models missing");
      const normalized: HotKeyAPI.SelectBenchImportInput["models"] = {};
      for (const [name, value] of Object.entries(models)) {
        if (Array.isArray(value)) {
          normalized[name] = value;
          continue;
        }
        if (
          !value ||
          typeof value !== "object" ||
          !("cases" in value) ||
          !Array.isArray(value.cases)
        )
          throw new Error("cases missing");
        normalized[name] = value.cases.map((item: Record<string, unknown>) => ({
          case_id: item.caseId,
          title: item.title,
          gold: item.gold,
          stratum: item.stratum ?? null,
          decision: item.decision ?? null,
          score: item.score ?? null,
          relevance: item.relevance ?? null,
          category: item.category ?? null,
          reason: item.reason ?? null,
          error_code: item.error ? "imported_model_error" : null,
        }));
      }
      const meta =
        parsed.meta && typeof parsed.meta === "object"
          ? (parsed.meta as Record<string, unknown>)
          : parsed;
      const input = {
        label,
        reason,
        prompt_version: prompt,
        models: normalized,
        split: typeof meta.split === "string" ? meta.split : null,
        seed: typeof meta.seed === "number" ? meta.seed : null,
      };
      const payload = JSON.stringify(input);
      if (identity.current?.payload !== payload)
        identity.current = { payload, id: crypto.randomUUID() };
      const row = await importOperatorSelectBench(
        { ...input, operation_id: identity.current.id },
        options,
      );
      identity.current = null;
      setRuns((v) => [row, ...v.filter((item) => item.id !== row.id)]);
      setSelected(row.id);
      setMessage("评测已导入，指标由服务端按逐条结果重新计算。");
      setFile(null);
      setBusy(false);
      await load(row.id);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="grid gap-5">
      <h2 className="text-xl font-semibold">SelectBench 筛选评测</h2>
      <p className="text-muted-foreground text-sm">
        同一批黄金样本比较模型。失败结果保留为空；导入报告不会发起模型调用。
      </p>
      <SelectBenchRunner
        token={token}
        accepted={(run) => {
          setRuns((old) => [run, ...old.filter((row) => row.id !== run.id)]);
          void load(run.id);
        }}
      />
      {selected && (
        <Button variant="secondary" onClick={() => void load()}>
          刷新当前评测
        </Button>
      )}
      <form onSubmit={importReport}>
        <FieldGroup className="grid gap-3 sm:grid-cols-2">
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-1`}>
              评测名称
            </FieldLabel>
            <Input
              required
              maxLength={200}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              id={`${fieldId}-selectbench-reading-field-1`}
            />
          </Field>
          <Field className="min-w-0">
            <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-2`}>
              提示词版本
            </FieldLabel>
            <Input
              required
              maxLength={100}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              id={`${fieldId}-selectbench-reading-field-2`}
            />
          </Field>
          <Field className="min-w-0 sm:col-span-2">
            <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-3`}>
              导入原因
            </FieldLabel>
            <Input
              required
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              id={`${fieldId}-selectbench-reading-field-3`}
            />
          </Field>
          <Field className="min-w-0 sm:col-span-2">
            <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-4`}>
              评测 JSON（最多 20 MiB）
            </FieldLabel>
            <Input
              type="file"
              accept="application/json,.json"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              id={`${fieldId}-selectbench-reading-field-4`}
            />
          </Field>
          <Button type="submit" disabled={busy} className="justify-self-start">
            导入并复算评测
          </Button>
        </FieldGroup>
      </form>
      <div className="flex flex-wrap gap-2">
        {runs.map((row) => (
          <Button
            key={row.id}
            variant={selected === row.id ? "secondary" : "ghost"}
            onClick={() => void load(row.id)}
          >
            {row.label} · {row.sample_size} 条
          </Button>
        ))}
      </div>
      {cases && (
        <>
          <p className="text-muted-foreground text-sm break-all">
            黄金集 {cases.run.gold_fingerprint} · {cases.run.prompt_version} ·{" "}
            {cases.run.split ?? "无分组"} · seed {cases.run.seed ?? "未知"}
          </p>
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
              >
                <span className="min-w-0 text-left">指标与阈值扫描</span>
                <ChevronDownIcon
                  aria-hidden="true"
                  data-icon="inline-end"
                  className="group-data-[state=open]:rotate-180"
                />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent
              forceMount
              className="data-[state=closed]:hidden"
            >
              <pre className="bg-muted/40 mt-3 max-h-96 overflow-auto rounded-lg p-4 text-xs">
                {JSON.stringify(cases.run.summary, null, 2)}
              </pre>
            </CollapsibleContent>
          </Collapsible>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void load();
            }}
          >
            <FieldGroup className="grid gap-3 sm:grid-cols-4">
              <Field className="min-w-0">
                <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-5`}>
                  模型
                </FieldLabel>
                <Select
                  value={model}
                  onValueChange={(selectedValue) =>
                    setModel(selectedValue === "__none__" ? "" : selectedValue)
                  }
                >
                  <SelectTrigger
                    id={`${fieldId}-selectbench-reading-field-5`}
                    className="w-full min-w-0"
                  >
                    <SelectValue placeholder="全部模型" />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">模型</SelectLabel>
                      <SelectItem
                        value="__none__"
                        className="whitespace-normal"
                      >
                        全部模型
                      </SelectItem>
                      {cases.run.models.map((name) => (
                        <SelectItem
                          key={name}
                          value={name}
                          className="whitespace-normal"
                        >
                          {name}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field className="min-w-0">
                <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-6`}>
                  误判类型
                </FieldLabel>
                <Select
                  value={outcome}
                  onValueChange={(selectedValue) =>
                    setOutcome(
                      selectedValue === "__none__" ? "" : selectedValue,
                    )
                  }
                >
                  <SelectTrigger
                    id={`${fieldId}-selectbench-reading-field-6`}
                    className="w-full min-w-0"
                  >
                    <SelectValue placeholder="全部" />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectGroup>
                      <SelectLabel className="sr-only">误判类型</SelectLabel>
                      <SelectItem
                        value="__none__"
                        className="whitespace-normal"
                      >
                        全部
                      </SelectItem>
                      {["tp", "fp", "tn", "fn", "either", "error"].map(
                        (name) => (
                          <SelectItem
                            key={name}
                            value={name}
                            className="whitespace-normal"
                          >
                            {name}
                          </SelectItem>
                        ),
                      )}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field className="min-w-0">
                <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-7`}>
                  样本分层
                </FieldLabel>
                <Input
                  value={stratum}
                  onChange={(e) => setStratum(e.target.value)}
                  id={`${fieldId}-selectbench-reading-field-7`}
                />
              </Field>
              <Field orientation="horizontal" className="w-auto">
                <Checkbox
                  checked={disagree}
                  onCheckedChange={(checked) => setDisagree(checked === true)}
                  id={`${fieldId}-selectbench-reading-field-8`}
                />
                <FieldLabel htmlFor={`${fieldId}-selectbench-reading-field-8`}>
                  仅模型分歧
                </FieldLabel>
              </Field>
              <Button
                disabled={busy}
                type="submit"
                className="justify-self-start"
              >
                应用评测筛选
              </Button>
            </FieldGroup>
          </form>
          <div className="grid gap-4">
            {cases.items.map((row) => (
              <article
                key={row.case_id}
                className="bg-muted/40 min-w-0 rounded-lg p-4"
              >
                <h3 className="font-medium">{row.title}</h3>
                <p className="text-muted-foreground text-sm">
                  {row.case_id} · gold {row.gold} · {row.stratum ?? "未分层"}
                </p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {Object.entries(row.by_model).map(([name, value]) => {
                    const result = value as HotKeyAPI.SelectBenchCaseInput;
                    return (
                      <div key={name} className="min-w-0">
                        <p className="break-all">
                          {name} · {result.decision ?? "结果失败"} ·{" "}
                          {result.score == null
                            ? "分数未知"
                            : `${result.score} 分`}
                        </p>
                        <p className="text-muted-foreground text-sm">
                          {result.error_code ?? result.reason ?? "无理由说明"}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
          {cases.next_cursor && (
            <Button
              disabled={busy}
              className="justify-self-start"
              variant="ghost"
              onClick={() => void load(selected, cases.next_cursor!)}
            >
              加载更多评测样本
            </Button>
          )}
        </>
      )}
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}
