"use client";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { useState } from "react";
import { ChevronDownIcon } from "lucide-react";

import { formatTime } from "@/app/content/components/content-presenters";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import {
  SelectLabel,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Annotation = HotKeyAPI.ContentAnnotationReadView;
type Topic = HotKeyAPI.ContentAnalysisTopicView;

export function selectedAnnotation(
  annotations: Annotation[],
  topic: Topic,
  versionId: string,
  promptVersion: string,
): { current: Annotation | null; historical: Annotation[] } {
  const scoped = annotations.filter(
    (item) =>
      item.topic_id === topic.topic_id && item.content_version_id === versionId,
  );
  const current =
    scoped.find(
      (item) =>
        item.topic_rule_version === topic.current_rule_version &&
        item.prompt_version === promptVersion,
    ) ?? null;
  return {
    current,
    historical: scoped.filter((item) => item.id !== current?.id),
  };
}

function sentimentLabel(value: Annotation["sentiment"]): string {
  if (value === "positive") return "正向";
  if (value === "negative") return "负向";
  if (value === "neutral") return "中性";
  return "未标注";
}

export function AnnotationResult({
  annotation,
  historical,
}: {
  annotation: Annotation | null;
  historical: boolean;
}) {
  if (annotation === null) {
    return (
      <div className="mt-6 py-4">
        <Badge variant="outline">暂无标注记录</Badge>
        <p className="text-muted-foreground mt-3 text-sm leading-6">
          此主题、正文版本、规则与提示词组合尚无分析结果；不能将无记录当作不相关。
        </p>
      </div>
    );
  }

  const label =
    annotation.result_state === "valid"
      ? annotation.relevant
        ? "相关"
        : "不相关"
      : annotation.result_state === "pending"
        ? "等待标注"
        : annotation.result_state === "failed"
          ? "标注失败"
          : "标注无效";

  return (
    <article className="mt-6 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            annotation.result_state === "valid" ? "secondary" : "outline"
          }
        >
          {label}
        </Badge>
        {historical ? <Badge variant="outline">历史结果</Badge> : null}
        <span className="text-muted-foreground text-xs">
          主题规则 v{annotation.topic_rule_version} ·{annotation.prompt_version}
        </span>
      </div>
      {annotation.result_state === "valid" ? (
        <>
          <p className="mt-4 text-sm leading-6 break-words whitespace-pre-wrap">
            判断理由：{annotation.relevance_reason}
          </p>
          <p className="mt-2 text-sm leading-6 break-words whitespace-pre-wrap">
            摘要：{annotation.summary}
          </p>
          {annotation.relevant ? (
            <p className="text-muted-foreground mt-2 text-sm">
              情感：{sentimentLabel(annotation.sentiment)}
            </p>
          ) : null}
          {annotation.viewpoints.length > 0 ? (
            <ul className="mt-3 flex list-disc flex-col gap-1 pl-5 text-sm leading-6">
              {annotation.viewpoints.map((viewpoint, index) => (
                <li key={`${index}-${viewpoint}`} className="break-words">
                  {viewpoint}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : (
        <p className="text-muted-foreground mt-3 text-sm leading-6">
          {annotation.result_state === "pending"
            ? "分析任务尚未产生有效结论。"
            : `没有有效相关性结论${annotation.error_code ? `，原因代码：${annotation.error_code}` : ""}。`}
        </p>
      )}
      <p className="text-muted-foreground mt-3 text-xs">
        最近更新 {formatTime(annotation.updated_at)}
      </p>
    </article>
  );
}

export function AnnotationPanel({
  content,
}: {
  content: HotKeyAPI.ContentRecordDetailView;
}) {
  const currentVersionId =
    content.latest_observation.content_version?.id ?? null;
  const [topicId, setTopicId] = useState(
    content.analysis_topics[0]?.topic_id ?? "",
  );
  const [versionId, setVersionId] = useState(
    currentVersionId ?? content.version_history[0]?.content_version.id ?? "",
  );
  const topic = content.analysis_topics.find(
    (item) => item.topic_id === topicId,
  );
  const selection = topic
    ? selectedAnnotation(
        content.annotations,
        topic,
        versionId,
        content.analysis_prompt_version,
      )
    : null;
  const isCurrentVersion = versionId === currentVersionId;

  return (
    <section aria-labelledby="annotation-heading" className="mt-10">
      <h2 id="annotation-heading" className="text-xl font-medium">
        主题分析
      </h2>
      <p className="text-muted-foreground mt-2 text-sm leading-6">
        仅当前正文、主题规则与提示词版本一致的有效标注可作为当前结论。页面读取不会发起模型请求。
      </p>
      {content.analysis_topics.length === 0 ? (
        <p className="text-muted-foreground mt-4 text-sm">
          此作品尚无可关联的监控主题或标注记录。
        </p>
      ) : (
        <>
          <FieldGroup className="mt-6 grid gap-4 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="analysis-topic">监控主题</FieldLabel>
              <Select value={topicId} onValueChange={setTopicId}>
                <SelectTrigger id="analysis-topic" className="w-full min-w-0">
                  <SelectValue placeholder="选择主题" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel className="sr-only">监控主题</SelectLabel>
                    {content.analysis_topics.map((item) => (
                      <SelectItem key={item.topic_id} value={item.topic_id}>
                        {item.topic_name} · 规则 v{item.current_rule_version}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            {content.version_history.length > 0 ? (
              <Field>
                <FieldLabel htmlFor="analysis-version">正文版本</FieldLabel>
                <Select value={versionId} onValueChange={setVersionId}>
                  <SelectTrigger
                    id="analysis-version"
                    className="w-full min-w-0"
                  >
                    <SelectValue placeholder="选择版本" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectLabel className="sr-only">正文版本</SelectLabel>
                      {content.version_history.map((item) => (
                        <SelectItem
                          key={item.content_version.id}
                          value={item.content_version.id}
                        >
                          {item.content_version.id === currentVersionId
                            ? "当前正文"
                            : "历史正文"}{" "}
                          ·{formatTime(item.last_observed_at)}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
            ) : null}
          </FieldGroup>
          {topic && versionId ? (
            <>
              {!isCurrentVersion ? (
                <Alert role="status" className="mt-4">
                  <AlertDescription>
                    当前查看历史正文版本，以下结果不能代表现行正文。
                  </AlertDescription>
                </Alert>
              ) : null}
              <AnnotationResult
                annotation={selection?.current ?? null}
                historical={!isCurrentVersion}
              />
              {selection && selection.historical.length > 0 ? (
                <Collapsible className="mt-6">
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost">
                      旧规则或提示词结果
                      <ChevronDownIcon data-icon="inline-end" />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <p className="text-muted-foreground mt-1 text-sm">
                      以下记录不能替代当前版本的分析结论。
                    </p>
                    {selection.historical.map((item) => (
                      <AnnotationResult
                        key={item.id}
                        annotation={item}
                        historical
                      />
                    ))}
                  </CollapsibleContent>
                </Collapsible>
              ) : null}
            </>
          ) : (
            <Empty className="mt-4">
              <EmptyHeader>
                <EmptyDescription>暂无可分析的正文版本。</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
        </>
      )}
    </section>
  );
}
