import * as UI from "@/components/ui/content";

function quantity(value: number | null | undefined, unit: string): string {
  return value == null ? "未知" : `${value} ${unit}`;
}

function CountFact({
  label,
  value,
  explanation,
  denominator,
}: {
  label: string;
  value: string;
  explanation: string;
  denominator?: string;
}) {
  return (
    <UI.Content className="min-w-0">
      <UI.Content as="dt" className="text-muted-foreground text-xs">
        {label}
      </UI.Content>
      <UI.Content as="dd" className="mt-2 flex flex-col gap-2">
        <UI.Text className="font-mono text-lg tabular-nums">{value}</UI.Text>
        {denominator ? (
          <UI.Text className="text-muted-foreground text-xs">
            分母：{denominator}
          </UI.Text>
        ) : null}
        <UI.Text className="text-muted-foreground text-xs">
          {explanation}
        </UI.Text>
      </UI.Content>
    </UI.Content>
  );
}

export function CollectionIdentityCounts({
  row,
  headingLevel = 4,
}: {
  row: Partial<
    Pick<
      HotKeyAPI.CollectionCoverageView,
      | "identity_count_basis"
      | "observed_count"
      | "stored_observation_count"
      | "unique_content_count"
      | "inserted_count"
      | "updated_count"
      | "unchanged_count"
      | "unclassified_count"
      | "deduplicated_count"
    >
  >;
  headingLevel?: 2 | 4;
}) {
  const supported = row.identity_count_basis === "retained_receipt_identity_v1";
  const denominator = quantity(row.unique_content_count, "个唯一身份");
  const categories = [
    {
      label: "新增",
      count: row.inserted_count,
      explanation: "首次保留观察属于本任务。",
    },
    {
      label: "更新",
      count: row.updated_count,
      explanation: "已有身份的正文版本或已知指标发生变化。",
    },
    {
      label: "未变",
      count: row.unchanged_count,
      explanation: "仅表示已存正文版本与指标未变。",
    },
    {
      label: "无法比较",
      count: row.unclassified_count,
      explanation: "无已知变化，但缺正文版本或指标可得性变化。",
    },
  ];

  return (
    <UI.Content
      as="section"
      aria-label="采集计量"
      className="mt-8 flex flex-col gap-5"
    >
      <UI.Heading level={headingLevel} className="font-medium">
        采集计量
      </UI.Heading>
      <UI.Content as="dl" className="grid grid-cols-2 gap-6 sm:grid-cols-3">
        <CountFact
          label="上游返回"
          value={quantity(row.observed_count, "条")}
          explanation="精筛前返回的条数，可能含重复及窗口外材料。"
        />
        <CountFact
          label="持久观察"
          value={quantity(row.stored_observation_count, "条")}
          explanation="精筛后保存的观察；同身份可多次出现，操作重放不增加。"
        />
        <CountFact
          label="唯一身份"
          value={denominator}
          explanation="本任务持久观察按内容身份去重，是下列四类的共同分母。"
        />
      </UI.Content>
      <UI.Text className="text-muted-foreground text-sm">
        四类互斥，合计为本任务唯一身份数。不同分母不相加，不表示全平台覆盖率。
      </UI.Text>
      {!supported ? (
        <UI.Text className="text-muted-foreground text-sm">
          未提供可核对的身份计量口径，分类保持未知，不从旧计数推断。
        </UI.Text>
      ) : null}
      <UI.Content as="dl" className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        {categories.map((category) => (
          <CountFact
            key={category.label}
            label={category.label}
            value={quantity(supported ? category.count : null, "个身份")}
            denominator={supported ? denominator : "未知"}
            explanation={category.explanation}
          />
        ))}
      </UI.Content>
      <UI.Content as="dl">
        <CountFact
          label="旧口径重复观察"
          value={quantity(row.deduplicated_count, "条")}
          explanation="持久观察数减新增身份数，包含旧帖更新及同任务多次观察，不能作为未变数或与四类相加。"
        />
      </UI.Content>
      <UI.Text className="text-muted-foreground text-xs">
        分类依据当前保留的观察历史；删除历史后可能改变。新增身份在本任务内更新仍只记新增，正文与指标同时变化只记一次更新。未知不当零，不计算百分比。
      </UI.Text>
    </UI.Content>
  );
}
