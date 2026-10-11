import * as UI from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  eventSourceAnchor,
  type EventSource,
} from "@/components/events/reading-model";

const labels = {
  new_fact: "新事实材料",
  supplement: "补证",
  repeat: "重复转述",
  unknown: "未知",
};

function verifiedDelta(page: HotKeyAPI.EventFactPageView) {
  const delta = page.delta;
  if (
    page.delta_state !== "available" ||
    !delta ||
    delta.version !== "fact_delta_v1" ||
    delta.event_id !== page.event_id ||
    delta.event_revision !== page.event_revision ||
    !Number.isSafeInteger(delta.baseline_event_revision) ||
    delta.baseline_event_revision < 0 ||
    delta.event_revision !== delta.baseline_event_revision + 1 ||
    !Array.isArray(delta.material_changes) ||
    !delta.material_changes.length ||
    delta.material_changes.length > 20
  )
    return null;
  const changes = delta.material_changes;
  const counts = {
    new_fact_material_count: changes.filter((item) => item.kind === "new_fact")
      .length,
    supplement_count: changes.filter((item) => item.kind === "supplement")
      .length,
    repeat_count: changes.filter((item) => item.kind === "repeat").length,
    unknown_count: changes.filter((item) => item.kind === "unknown").length,
    material_count: changes.length,
    new_fact_count: new Set(
      changes
        .filter((item) => item.kind === "new_fact")
        .map((item) => item.fact_id),
    ).size,
  };
  if (
    new Set(changes.map((item) => item.event_member_id)).size !==
      changes.length ||
    new Set(changes.map((item) => item.content_version_id)).size !==
      changes.length ||
    counts.new_fact_material_count +
      counts.supplement_count +
      counts.repeat_count +
      counts.unknown_count !==
      changes.length ||
    changes.some(
      (item) =>
        !Object.hasOwn(labels, item.kind) ||
        (item.unavailable && (item.kind !== "unknown" || item.reason != null)),
    ) ||
    Object.entries(counts).some(
      ([key, value]) => delta[key as keyof typeof counts] !== value,
    )
  )
    return null;
  return delta;
}

export function EventFactDelta({
  page,
  sources,
}: {
  page: HotKeyAPI.EventFactPageView;
  sources: EventSource[];
}) {
  const delta = verifiedDelta(page);
  return (
    <UI.Content
      as="section"
      aria-label="自动归并修订变化"
      className="flex min-w-0 flex-col gap-3 rounded-lg border p-4"
    >
      <UI.Heading level={3}>自动归并修订变化</UI.Heading>
      {delta ? (
        <>
          <UI.Text size="sm" tone="muted">
            {delta.baseline_event_revision === 0
              ? "首次成案，空基准修订 0"
              : `基准事件修订 ${delta.baseline_event_revision}`}{" "}
            → 事件修订 {delta.event_revision}
            。仅比较这一次自动归并提交，不代表24小时变化。
          </UI.Text>
          <UI.Text>
            新增事实 <UI.InlineCode>{delta.new_fact_count}</UI.InlineCode>{" "}
            个（按事实身份去重，不以材料数作分母）
          </UI.Text>
          <UI.Content className="grid gap-2 sm:grid-cols-2">
            {(
              [
                ["新事实材料", delta.new_fact_material_count],
                ["补证", delta.supplement_count],
                ["重复转述", delta.repeat_count],
                ["未知", delta.unknown_count],
              ] as const
            ).map(([label, count]) => (
              <UI.Text key={label} size="sm">
                {label}{" "}
                <UI.InlineCode>
                  {count} / {delta.material_count}
                </UI.InlineCode>{" "}
                份新增材料
              </UI.Text>
            ))}
          </UI.Content>
          <UI.Text size="sm" tone="muted">
            四类互斥，分母只含本次实际新增的固定材料，不含既有上下文。补证与重复是模型判断，仍需核对原文；材料和来源数不代表独立证实。
          </UI.Text>
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button variant="outline" size="sm">
                逐材料核对变化
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-3 flex flex-col gap-3">
              {delta.material_changes.map((change) => {
                const source = sources.find(
                  (item) => item.id === change.event_member_id,
                );
                return (
                  <UI.Content
                    key={change.event_member_id}
                    className="flex min-w-0 flex-col gap-2 border-t pt-3"
                  >
                    <UI.Content className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary">{labels[change.kind]}</Badge>
                      {source ? (
                        <UI.TextLink
                          href={`#${eventSourceAnchor(source.id)}`}
                          aria-label={`变化来源 ${source.number}`}
                        >
                          固定来源 [{source.number}]
                        </UI.TextLink>
                      ) : (
                        <UI.Text size="sm" tone="muted">
                          固定来源待读取
                        </UI.Text>
                      )}
                    </UI.Content>
                    {change.unavailable ? (
                      <UI.Text size="sm" tone="muted">
                        证据不可读或关联已变，原判断隐藏。
                      </UI.Text>
                    ) : change.reason ? (
                      <UI.Text
                        size="sm"
                        className="wrap-anywhere whitespace-pre-wrap"
                      >
                        {change.reason}
                      </UI.Text>
                    ) : change.kind === "unknown" ? (
                      <UI.Text size="sm" tone="muted">
                        未保存可靠分类，保持未知。
                      </UI.Text>
                    ) : null}
                  </UI.Content>
                );
              })}
            </CollapsibleContent>
          </Collapsible>
        </>
      ) : (
        <UI.Text size="sm" tone="muted">
          本次修订没有可核对的自动归并差分，数量未知。旧记录、人工纠错或无效回执不推算为零变化。
        </UI.Text>
      )}
    </UI.Content>
  );
}
