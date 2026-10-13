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
  desktopActions?: boolean;
  breadcrumbs?: readonly { label: string; href?: string }[];
  children?: ReactNode;
};

export function PageHeader({
  title,
  titleId,
  titleAppearance,
  description,
  actions,
  desktopActions = false,
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
          "flex min-w-0 flex-col flex-wrap justify-between gap-4 @min-[40rem]/page:flex-row",
          description
            ? "@min-[40rem]/page:items-end"
            : "@min-[40rem]/page:items-center",
        )}
      >
        <UI.Content className="flex min-w-0 flex-1 flex-col gap-1 @min-[40rem]/page:basis-64 @min-[40rem]/page:gap-2">
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
              "flex w-full max-w-full min-w-0 flex-wrap items-center gap-3 @min-[40rem]/page:w-auto",
              description && "@min-[40rem]/page:mb-px",
              desktopActions && "hidden @min-[40rem]/page:flex",
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
