import * as UI from "@/components/ui/content";
import type { ReactNode } from "react";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Field, FieldGroup } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";

export function LoginFormLayout({
  children,
  loading = false,
}: {
  children: ReactNode;
  loading?: boolean;
}) {
  return (
    <UI.Content
      as="section"
      aria-labelledby="login-title"
      className="mx-auto w-full max-w-md min-w-0 lg:mr-0"
    >
      <Card variant="muted" className="gap-5 py-5 sm:gap-6 sm:py-8">
        <CardHeader className="gap-2 px-5 sm:px-8">
          <UI.Heading level={1} id="login-title">
            登录Ripplesight
          </UI.Heading>
          <UI.Text tone="muted" size="sm">
            继续关注你在意的，沿着来源看见变化。
          </UI.Text>
        </CardHeader>
        <CardContent className="px-5 sm:px-8">
          <UI.Content aria-busy={loading}>{children}</UI.Content>
        </CardContent>
        <CardContent className="px-5 sm:px-8">
          <UI.Text tone="muted" size="xs">
            登录即表示你已阅读
            <UI.TextLink href="/terms">使用条款</UI.TextLink>与
            <UI.TextLink href="/privacy">隐私说明</UI.TextLink>
            。本站仅供个人非商业使用。
          </UI.Text>
        </CardContent>
      </Card>
    </UI.Content>
  );
}

export function LoginFormSkeleton() {
  return (
    <UI.Content role="status" aria-label="正在读取登录方式">
      <UI.Text as="span" className="sr-only">
        正在读取登录方式…
      </UI.Text>
      <UI.Content aria-hidden="true">
        <UI.Content className="mb-5 flex gap-2">
          <Skeleton className="h-9 flex-1 motion-reduce:animate-none" />
          <Skeleton className="h-9 flex-1 motion-reduce:animate-none" />
        </UI.Content>
        <FieldGroup>
          {["username", "password"].map((field) => (
            <Field key={field}>
              <Skeleton className="h-5 max-w-24 motion-reduce:animate-none" />
              <Skeleton className="h-8 motion-reduce:animate-none" />
            </Field>
          ))}
          <Skeleton className="h-9 motion-reduce:animate-none" />
        </FieldGroup>
        <UI.Content className="mt-5 flex flex-col gap-4">
          <Skeleton className="h-4 motion-reduce:animate-none" />
          <Skeleton className="h-9 motion-reduce:animate-none" />
        </UI.Content>
      </UI.Content>
    </UI.Content>
  );
}
