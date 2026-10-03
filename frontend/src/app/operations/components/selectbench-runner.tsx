"use client";
import { toast } from "sonner";
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { useId, useRef, useState, useEffect } from "react";
import Link from "next/link";
import { runOperatorSelectBench } from "@/api/yunyingweihu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiRequestError } from "@/request";

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("gold format");
  return value as Record<string, unknown>;
}
export function normalizeGold(
  input: string,
): HotKeyAPI.SelectBenchGoldCaseInput[] {
  const trimmed = input.trim();
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    parsed = trimmed
      .split(/\r?\n/)
      .filter((line) => line.trim())
      .map((line) => JSON.parse(line));
  }
  const rows = Array.isArray(parsed) ? parsed : record(parsed).cases;
  if (!Array.isArray(rows) || !rows.length || rows.length > 5000)
    throw new Error("gold cases missing");
  return rows.map((value) => {
    const row = record(value);
    if (typeof row.case_id === "string")
      return row as HotKeyAPI.SelectBenchGoldCaseInput;
    const material = record(row.material);
    const source = record(row.sourceFacts);
    const sampling = row.samplingContext ? record(row.samplingContext) : {};
    const gold = record(row.gold);
    if (
      typeof row.caseId !== "string" ||
      typeof material.title !== "string" ||
      !["select", "reject", "either"].includes(String(gold.decision))
    )
      throw new Error("invalid gold case");
    return {
      case_id: row.caseId,
      title: material.title,
      body: String(material.bodyZh ?? material.bodyOriginal ?? ""),
      gold: gold.decision as HotKeyAPI.SelectBenchGoldCaseInput["gold"],
      tier: String(source.sourceTier ?? "T2").replace(
        ".",
        "_",
      ) as HotKeyAPI.SelectBenchGoldCaseInput["tier"],
      first_party: source.firstParty === true,
      source_kind: (typeof source.sourceKind === "string"
        ? source.sourceKind
        : "rss") as HotKeyAPI.SelectBenchGoldCaseInput["source_kind"],
      source_name:
        typeof material.sourceName === "string"
          ? material.sourceName
          : "黄金样本",
      published_at:
        typeof material.publishedAt === "string" ? material.publishedAt : null,
      stratum:
        typeof sampling.samplingStratum === "string"
          ? sampling.samplingStratum
          : null,
      split:
        typeof sampling.benchmarkSplit === "string"
          ? sampling.benchmarkSplit
          : null,
    };
  });
}

export function SelectBenchRunner({
  token,
  accepted,
}: {
  token: string;
  accepted: (run: HotKeyAPI.SelectBenchRunView) => void;
}) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fieldId = useId();

  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [models, setModels] = useState("");
  const [reason, setReason] = useState("");
  const [split, setSplit] = useState("");
  const [sample, setSample] = useState("100");
  const [seed, setSeed] = useState("42");
  const [busy, setBusy] = useState(false);

  const [jobIds, setJobIds] = useState<string[]>([]);
  const operation = useRef<{ payload: string; id: string } | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("gold too large");
      const input = {
        label,
        reason,
        models: models
          .split(/[,\n]/)
          .map((value) => value.trim())
          .filter(Boolean),
        cases: normalizeGold(await file.text()),
        sample_size: Number(sample),
        seed: Number(seed),
        split: split || null,
      };
      const payload = JSON.stringify(input);
      if (operation.current?.payload !== payload)
        operation.current = { payload, id: crypto.randomUUID() };
      const result = await runOperatorSelectBench(
        { ...input, operation_id: operation.current.id },
        { headers: { "X-HotKey-Operator-Token": token } },
      );
      if (!mounted.current) return;
      operation.current = null;
      setJobIds(result.job_ids);
      accepted(result.run);
      if (mounted.current)
        toast.success(
          `评测已受理：${result.run.sample_size} 条样本，${result.job_ids.length} 个原任务。请刷新评测结果查看进度。`,
        );
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (mounted.current)
        toast.error(
          error instanceof ApiRequestError
            ? error.message
            : "黄金集格式无效或评测未受理，请保留输入后重试。",
        );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Collapsible className="bg-muted/30 rounded-lg p-4">
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
        >
          <span className="min-w-0 text-left">运行生产筛选链路评测</span>
          <ChevronDownIcon
            aria-hidden="true"
            data-icon="inline-end"
            className="group-data-[state=open]:rotate-180"
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent forceMount className="data-[state=closed]:hidden">
        <p className="text-muted-foreground my-3 text-sm">
          使用当前预筛选与两次独立评分，按固定 seed
          分层抽样；会使用配置模型额度。运行开关默认关闭，失败或未知结果保留，未知付费阶段须人工复核。
        </p>
        <form onSubmit={submit}>
          <FieldGroup className="grid gap-3 sm:grid-cols-2">
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-selectbench-runner-field-1`}>
                运行评测名称
              </FieldLabel>
              <Input
                required
                maxLength={200}
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                id={`${fieldId}-selectbench-runner-field-1`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-selectbench-runner-field-2`}>
                模型名称（逗号分隔，最多 5 个）
              </FieldLabel>
              <Input
                required
                value={models}
                onChange={(e) => setModels(e.target.value)}
                id={`${fieldId}-selectbench-runner-field-2`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-selectbench-runner-field-3`}>
                抽样上限（1–100）
              </FieldLabel>
              <Input
                required
                type="number"
                min={1}
                max={100}
                value={sample}
                onChange={(e) => setSample(e.target.value)}
                id={`${fieldId}-selectbench-runner-field-3`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-selectbench-runner-field-4`}>
                固定 seed
              </FieldLabel>
              <Input
                required
                type="number"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                id={`${fieldId}-selectbench-runner-field-4`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-selectbench-runner-field-5`}>
                split（可选）
              </FieldLabel>
              <Input
                value={split}
                onChange={(e) => setSplit(e.target.value)}
                id={`${fieldId}-selectbench-runner-field-5`}
              />
            </Field>
            <Field className="min-w-0">
              <FieldLabel htmlFor={`${fieldId}-selectbench-runner-field-6`}>
                运行原因
              </FieldLabel>
              <Input
                required
                maxLength={2000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                id={`${fieldId}-selectbench-runner-field-6`}
              />
            </Field>
            <Field className="min-w-0 sm:col-span-2">
              <FieldLabel htmlFor={`${fieldId}-selectbench-runner-field-7`}>
                黄金集 JSON / AIHOT JSONL（最多 20 MiB）
              </FieldLabel>
              <Input
                required
                type="file"
                accept="application/json,.json,.jsonl"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                id={`${fieldId}-selectbench-runner-field-7`}
              />
            </Field>
            <Button type="submit" disabled={busy}>
              受理模型评测任务
            </Button>
          </FieldGroup>
        </form>

        {jobIds.length > 0 && (
          <div className="mt-3 flex max-h-32 flex-wrap gap-2 overflow-auto text-xs">
            {jobIds.map((id) => (
              <Link key={id} href={`/jobs/${id}`} className="underline">
                任务 {id.slice(0, 8)}
              </Link>
            ))}
          </div>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
