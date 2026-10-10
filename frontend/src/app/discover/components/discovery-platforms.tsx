"use client";
import { AuthLink } from "@/components/auth/auth-link";
import { Button } from "@/components/ui/button";
import { useId } from "react";
import { useRouter } from "next/navigation";
import { Content, Heading, Text } from "@/components/ui/content";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { discoveryHref } from "./discovery-data";
export function DiscoveryPlatforms({
  sources,
  params,
  failed = false,
}: {
  failed?: boolean;
  sources: { key: string; name: string }[];
  params: Record<string, string | undefined>;
}) {
  const id = useId();
  const router = useRouter();
  return (
    <Content as="section" layout="stack">
      <Heading level={2} appearance="sidebar">
        信息来源
      </Heading>
      <Text size="sm" tone="muted">
        公开来源由站点配置，勾选可筛选当前结果。
      </Text>
      <FieldGroup className="gap-3">
        {sources.length ? (
          sources.map((source) => (
            <Field key={source.key} orientation="horizontal">
              <Checkbox
                id={`${id}-${source.key}`}
                checked={params.source_key === source.key}
                onCheckedChange={(checked) =>
                  router.push(
                    discoveryHref({
                      ...params,
                      source_key: checked ? source.key : undefined,
                    }),
                  )
                }
              />
              <FieldLabel htmlFor={`${id}-${source.key}`}>
                {source.name}
              </FieldLabel>
            </Field>
          ))
        ) : (
          <Text size="sm" tone="muted">
            {failed ? "来源列表暂时无法读取。" : "站点尚未配置公开来源。"}
          </Text>
        )}
      </FieldGroup>
      <Button asChild variant="outline" size="sm" className="self-start">
        <AuthLink href="/sources/personal">管理我的来源</AuthLink>
      </Button>
    </Content>
  );
}
