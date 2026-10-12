import { cn } from "@/lib/utils";
import { Fragment, type ReactNode } from "react";
import Link from "next/link";

import * as UI from "@/components/ui/content";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

type PageHeaderProps = {
  title: ReactNode;
  titleId?: string;
  titleAppearance?: React.ComponentProps<typeof UI.Heading>["appearance"];
  description?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: readonly { label: string; href?: string }[];
  children?: ReactNode;
};

export function PageHeader({
  title,
  titleId,
  titleAppearance,
  description,
  actions,
  breadcrumbs,
  children,
}: PageHeaderProps) {
  return (
    <UI.Content as="header" className="flex min-w-0 flex-col gap-4">
      {breadcrumbs?.length ? (
        <Breadcrumb aria-label="面包屑">
          <BreadcrumbList>
            {breadcrumbs.map((item, index) => (
              <Fragment key={`${item.href ?? "current"}-${index}`}>
                {index > 0 && <BreadcrumbSeparator />}
                <BreadcrumbItem>
                  {item.href ? (
                    <BreadcrumbLink asChild>
                      <Link href={item.href}>{item.label}</Link>
                    </BreadcrumbLink>
                  ) : (
                    <BreadcrumbPage>{item.label}</BreadcrumbPage>
                  )}
                </BreadcrumbItem>
              </Fragment>
            ))}
          </BreadcrumbList>
        </Breadcrumb>
      ) : null}
      <UI.Content
        className={cn(
          "flex min-w-0 flex-col flex-wrap justify-between gap-4 md:flex-row",
          description ? "md:items-end" : "md:items-center",
        )}
      >
        <UI.Content className="flex min-w-0 flex-1 flex-col gap-2 md:basis-64">
          <UI.Heading
            level={1}
            appearance={titleAppearance}
            id={titleId}
            className="break-words"
          >
            {title}
          </UI.Heading>
          {description && (
            <UI.Text tone="muted" size="description">
              {description}
            </UI.Text>
          )}
        </UI.Content>
        {actions && (
          <UI.Content
            className={cn(
              "flex max-w-full shrink-0 flex-wrap items-center gap-3",
              description && "md:mb-px",
            )}
          >
            {actions}
          </UI.Content>
        )}
      </UI.Content>
      {children}
    </UI.Content>
  );
}
