import * as UI from "@/components/ui/content";
import Link from "next/link";
import type { ReactNode } from "react";

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
      className="mx-auto w-full max-w-104 lg:mr-0 lg:translate-y-6"
    >
      <UI.Content className="mb-9 flex flex-col gap-y-3">
        <UI.Heading
          level={1}
          id="login-title"
          className="text-3xl font-medium tracking-tight"
        >
          登录知微见澜
        </UI.Heading>
        <UI.Text className="text-muted-foreground text-sm leading-6">
          继续关注你在意的，沿着来源看见变化。
        </UI.Text>
      </UI.Content>
      <UI.Content className="min-h-124" aria-busy={loading}>
        {children}
      </UI.Content>
      <UI.Text className="text-muted-foreground mt-8 text-xs leading-6">
        登录即表示你已阅读
        <Link
          href="/terms"
          className="text-foreground underline underline-offset-4"
        >
          使用条款
        </Link>
        与
        <Link
          href="/privacy"
          className="text-foreground underline underline-offset-4"
        >
          隐私说明
        </Link>
        。
      </UI.Text>
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
        <FieldGroup className="gap-6">
          {["username", "password"].map((field) => (
            <Field key={field}>
              <Skeleton className="h-5 max-w-24 motion-reduce:animate-none" />
              <Skeleton className="h-12 motion-reduce:animate-none" />
            </Field>
          ))}
          <Skeleton className="h-12 motion-reduce:animate-none" />
        </FieldGroup>
        <UI.Content className="mt-7 flex flex-col gap-3">
          <Skeleton className="mb-4 h-4 motion-reduce:animate-none" />
          <Skeleton className="h-12 motion-reduce:animate-none" />
          <Skeleton className="h-12 motion-reduce:animate-none" />
          <Skeleton className="h-5 w-36 motion-reduce:animate-none" />
        </UI.Content>
      </UI.Content>
    </UI.Content>
  );
}
