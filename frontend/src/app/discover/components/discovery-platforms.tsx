"use client";
import { useId } from "react";
import { useRouter } from "next/navigation";
import { Content, Heading, Text } from "@/components/ui/content";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { discoveryHref } from "./discovery-data";
export function DiscoveryPlatforms({
  sources,
  params,
}: {
  sources: { key: string; name: string }[];
  params: Record<string, string | undefined>;
}) {
  const id = useId();
  const router = useRouter();
  return (
    <Content as="section" layout="stack">
      <Heading level={2} appearance="sidebar">
        平台
      </Heading>
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
            暂无可筛选的平台。
          </Text>
        )}
      </FieldGroup>
    </Content>
  );
}
